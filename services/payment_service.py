"""Pagos y recibos."""

import uuid
from datetime import datetime

from core.database import get_db
from core.dtos import PaymentDTO
from core.patterns import MockGatewayAdapter, PaymentErrorFacade, PedidoEstadoMachine, get_canal_eventos


class PaymentError(Exception):
    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo


class PaymentService:
    def __init__(self, gateway_adapter=None):
        self.db = get_db()
        self.gateway = gateway_adapter or MockGatewayAdapter()
        self.canal = get_canal_eventos()

    def preparar_pago(self, pedido_id: int, tipo_pago: str, cliente_id: int = None, **campos_pago):
        pedido = self._validar_pedido_pagable(pedido_id, cliente_id)
        dto = PaymentDTO(monto=pedido["monto_total"], tipo_pago=tipo_pago, **campos_pago)
        errores = dto.validar()
        if errores:
            raise PaymentError(" / ".join(errores))
        return dto

    def _validar_pedido_pagable(self, pedido_id: int, cliente_id: int = None):
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise PaymentError("Pedido no encontrado.")
        if cliente_id is not None and pedido["cliente_id"] != cliente_id:
            raise PaymentError("Este pedido no te pertenece.")
        if pedido["estado"] != "PENDIENTE_CHEF":
            raise PaymentError("Este pedido ya no está pendiente de pago.")

        from services.order_service import OrderService
        if not OrderService().pedido_fue_aceptado(pedido_id):
            raise PaymentError("El chef aún no ha aceptado este pedido.")
        return pedido

    # ---------------- HU-13: Procesar Pago (pasarela simulada) ----------------
    def procesar_pago(self, pedido_id: int, dto: PaymentDTO):
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise PaymentError("Pedido no encontrado.")

        pago_id = self.db.insertar("pagos", {
            "pedido_id": pedido_id, "metodo_pago": dto.tipo_pago, "monto": dto.monto,
            "referencia_pago": dto.referencia(), "fecha_pago": datetime.now().isoformat(),
            "confirmacion": None,
        })

        # Constancia explícita del envío de la información a la pasarela
        self.db.log_evento(
            pedido_id, pedido["cliente_id"], "INFO_FINANCIERA_ENVIADA_PASARELA",
            f"tipo_pago={dto.tipo_pago}, referencia={dto.referencia()}, monto={dto.monto}",
        )
        resultado = self.gateway.cobrar(dto, timeout_segundos=5.0)

        if not resultado["aprobado"]:
            # ---------------- HU-14: Notificar Error de Pago ----------------
            mensaje_amigable = PaymentErrorFacade.traducir(resultado["error"])
            self.db.actualizar("pagos", {"_id": pago_id}, {"$set": {"confirmacion": {
                "estado": "FALLIDO", "id_transaccion": None, "codigo_error": resultado["error"],
                "fecha": datetime.now().isoformat()}}})
            self.db.log_evento(pedido_id, pedido["cliente_id"], "PAGO_RECHAZADO", resultado["error"])
            raise PaymentError(mensaje_amigable, codigo=resultado["error"])

        nuevo_estado = PedidoEstadoMachine.transicionar(pedido["estado"], "PAGADO")
        ahora = datetime.now().isoformat()
        self.db.transaccion([
            ("actualizar", "pagos", {"_id": pago_id}, {"$set": {"confirmacion": {
                "estado": "APROBADO", "id_transaccion": resultado["id_transaccion"],
                "codigo_error": None, "fecha": ahora}}}),
            ("actualizar", "pedidos", {"_id": pedido_id},
             {"$set": {"estado": nuevo_estado, "fecha_actualizacion": ahora}}),
        ])
        recibo_texto = self._cerrar_pago_aprobado(
            pedido, f"{dto.tipo_pago} ({dto.referencia()})", resultado["id_transaccion"])
        return {"ok": True, "id_transaccion": resultado["id_transaccion"], "estado": nuevo_estado,
                "recibo": recibo_texto}

    def _cerrar_pago_aprobado(self, pedido: dict, medio_texto: str, id_transaccion: str) -> str:
        """Pasos comunes tras un pago aprobado: auditoría, recibo y notificación al chef."""
        pedido_id = pedido["id"]
        self.db.log_evento(pedido_id, pedido["cliente_id"], "PAGO_APROBADO", id_transaccion)

        recibo_texto = self._generar_texto_recibo(pedido_id, medio_texto, id_transaccion)
        if self.db.buscar_uno("recibos", {"pedido_id": pedido_id}) is None:
            self.db.insertar("recibos", {"pedido_id": pedido_id, "contenido": recibo_texto,
                                         "fecha_generacion": datetime.now().isoformat()})
        self.db.log_evento(pedido_id, pedido["cliente_id"], "RECIBO_GENERADO_Y_ENVIADO", "")

        self.canal.publicar("PEDIDO_PAGADO_CHEF", {
            "restaurante_id": pedido["restaurante_id"], "pedido_id": pedido_id,
        })
        return recibo_texto

    def historial_pago(self, pedido_id: int):
        return self.db.buscar("pagos", {"pedido_id": pedido_id}, orden=[("fecha_pago", -1)])

    def obtener_recibo(self, pedido_id: int):
        fila = self.db.buscar_uno("recibos", {"pedido_id": pedido_id})
        return fila["contenido"] if fila else None

    # ---------------- Recibo / ticket digital ----------------
    def _generar_texto_recibo(self, pedido_id: int, medio_texto: str, id_transaccion: str) -> str:
        from services.order_service import OrderService
        pedido, detalles = OrderService().detalle_pedido(pedido_id)
        restaurante = self.db.buscar_uno("restaurantes", {"_id": pedido["restaurante_id"]})
        cliente = self.db.buscar_uno("usuarios", {"_id": pedido["cliente_id"]})
        lineas = [
            "=" * 42,
            "        SABORLOCAL — RECIBO DE COMPRA",
            "=" * 42,
            f"Pedido:        #{pedido_id}",
            f"Restaurante:   {restaurante['nombre_restaurante']}",
            f"Cliente:       {cliente['nombre'] or cliente['correo_electronico']}",
            f"Fecha:         {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "-" * 42,
        ]
        for d in detalles:
            lineas.append(f"{d['cantidad']} x {d['nombre']:<22} ${d['subtotal']:>10,.0f}")
        lineas += [
            "-" * 42,
            f"Subtotal:      ${pedido['subtotal']:>10,.0f}",
            f"Comisión:      ${pedido['monto_comision']:>10,.0f}",
            f"TOTAL:         ${pedido['monto_total']:>10,.0f}",
            "-" * 42,
            f"Medio de pago: {medio_texto}",
            f"Transacción:   {id_transaccion}",
            f"Entrega:       {'Domicilio' if pedido['tipo_entrega']=='DOMICILIO' else 'Recoger en el local'}",
            "=" * 42,
            "   ¡Gracias por tu compra en SaborLocal!",
            "=" * 42,
        ]
        return "\n".join(lineas)
