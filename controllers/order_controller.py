"""Controlador de order."""
from flask import Blueprint
from controllers.common import *
from controllers import common as _common

# Helpers privados compartidos (los nombres con _ no se importan con *)
from controllers.common import _manejar_api_error, _no_encontrado, _metodo_no_permitido, _sin_base_de_datos, _bd_pide_autenticacion, _error_interno, _restaurante_publicado, _pedido_del_cliente, _restaurante_del_chef, _borrador, _borrador_json, _datos_perfil, _datos_platillo, _acciones_chef, _accion_de_chef

bp = Blueprint("order", __name__)

@bp.route("/api/v1/carrito", methods=["GET"])
@api_requiere_rol("CLIENTE")
def api_carrito():
    return api_ok(carrito_json())

@bp.route("/api/v1/carrito", methods=["DELETE"])
@api_requiere_rol("CLIENTE")
def api_carrito_vaciar():
    session["carrito"] = []
    return api_ok(carrito_json(), "Carrito vaciado.")

@bp.route("/api/v1/carrito/items", methods=["POST"])
@api_requiere_rol("CLIENTE")
def api_carrito_agregar():
    datos = cuerpo_json()
    restaurante_id = a_entero(datos.get("restaurante_id"), "restaurante_id")
    producto_id = a_entero(datos.get("producto_id"), "producto_id")
    cantidad = max(1, a_entero(datos.get("cantidad"), "cantidad", defecto=1))

    producto = RestaurantService().obtener_producto(producto_id)
    if producto is None or producto["restaurante_id"] != restaurante_id:
        raise ApiError("Ese producto ya no está disponible.", 404)

    carrito = session.get("carrito", [])
    if carrito and carrito[0]["restaurante_id"] != restaurante_id:
        raise ApiError("Ya tienes productos de otro restaurante en el carrito. Vacíalo antes de agregar de otro.", 409)

    ya_en_carrito = cantidad_en_carrito(producto_id)
    disponible = producto["inventario"] - ya_en_carrito
    if disponible <= 0:
        raise ApiError(f"No hay más unidades de '{producto['nombre']}' disponibles"
                       + (" (ya tienes todo el stock en tu carrito)." if ya_en_carrito else "."), 409)

    mensaje, nivel = f"'{producto['nombre']}' agregado al carrito.", "success"
    if cantidad > disponible:
        mensaje = (f"Solo puedes agregar {disponible} unidad(es) más de '{producto['nombre']}'. "
                   "Se agregó el máximo disponible.")
        nivel, cantidad = "warning", disponible

    for item in carrito:
        if item["producto_id"] == producto_id:
            item["cantidad"] += cantidad
            break
    else:
        carrito.append({"restaurante_id": restaurante_id, "producto_id": producto_id,
                        "nombre": producto["nombre"], "precio": producto["precio"], "cantidad": cantidad})
    session["carrito"] = carrito
    return api_ok(carrito_json(), mensaje, 201, level=nivel)

@bp.route("/api/v1/carrito/items/<int:producto_id>", methods=["PATCH"])
@api_requiere_rol("CLIENTE")
def api_carrito_actualizar(producto_id):
    """Cambia la cantidad de un producto ya agregado (respetando el stock)."""
    datos = cuerpo_json()
    nueva = a_entero(datos.get("cantidad"), "cantidad", defecto=1)
    carrito = session.get("carrito", [])
    if not any(i["producto_id"] == producto_id for i in carrito):
        raise ApiError("Ese producto no está en tu carrito.", 404)

    if nueva <= 0:
        session["carrito"] = [i for i in carrito if i["producto_id"] != producto_id]
        return api_ok(carrito_json(), "Producto quitado del carrito.")

    producto = RestaurantService().obtener_producto(producto_id)
    if producto is None:
        session["carrito"] = [i for i in carrito if i["producto_id"] != producto_id]
        return api_ok(carrito_json(), "Ese producto ya no está disponible; se quitó del carrito.", level="warning")

    mensaje, nivel = "Cantidad actualizada.", "success"
    if nueva > producto["inventario"]:
        mensaje = f"Solo hay {producto['inventario']} unidades disponibles de '{producto['nombre']}'."
        nivel, nueva = "warning", max(1, producto["inventario"])
    for item in carrito:
        if item["producto_id"] == producto_id:
            item["cantidad"] = nueva
            break
    session["carrito"] = carrito
    return api_ok(carrito_json(), mensaje, level=nivel)

@bp.route("/api/v1/carrito/items/<int:producto_id>", methods=["DELETE"])
@api_requiere_rol("CLIENTE")
def api_carrito_quitar(producto_id):
    session["carrito"] = [i for i in session.get("carrito", []) if i["producto_id"] != producto_id]
    return api_ok(carrito_json(), "Producto quitado del carrito.")

@bp.route("/api/v1/pedidos", methods=["POST"])
@api_requiere_rol("CLIENTE")
def api_crear_pedido():
    """Checkout: convierte el carrito en un pedido."""
    datos = cuerpo_json()
    carrito = session.get("carrito", [])
    if not carrito:
        raise ApiError("Tu carrito está vacío.", 400)

    tipo_entrega = a_texto(datos.get("tipo_entrega") or "DOMICILIO")
    direccion = a_texto(datos.get("direccion"))
    try:
        RestaurantService.validar_tipo_entrega(tipo_entrega, direccion)
        pedido_id = OrderService().crear_pedido(
            cliente_id=usuario_actual()["id"],
            restaurante_id=carrito[0]["restaurante_id"],
            carrito=[{"producto_id": i["producto_id"], "cantidad": i["cantidad"]} for i in carrito],
            tipo_entrega=tipo_entrega,
            direccion_entrega=direccion if tipo_entrega == "DOMICILIO" else None,
        )
    except RestaurantError as e:
        raise ApiError(str(e), 400)
    except OrderError as e:
        raise ApiError(str(e), 409)
    session["carrito"] = []
    return api_ok({"pedido_id": pedido_id, "estado": "PENDIENTE_CHEF", "redirect": "/cliente/pedidos"},
                  f"Pedido #{pedido_id} creado. Espera a que el restaurante lo confirme.", 201)

@bp.route("/api/v1/pedidos", methods=["GET"])
@api_requiere_rol("CLIENTE")
def api_pedidos_cliente():
    ordenes, resenas = OrderService(), ReviewService()
    data = []
    for p in ordenes.listar_pedidos_de_cliente(usuario_actual()["id"]):
        aceptado = ordenes.pedido_fue_aceptado(p["id"])
        calificado = resenas.pedido_calificado(p["id"])
        data.append(pedido_json(p) | {
            "aceptado_por_chef": aceptado,
            "calificado": calificado,
            "puede_pagar": p["estado"] == "PENDIENTE_CHEF" and aceptado,
            "puede_confirmar": p["estado"] in ("EN_TRANSITO", "LISTO_PARA_RECOGER"),
            "puede_calificar": p["estado"] == "COMPLETADO" and not calificado,
            "tiene_recibo": p["estado"] in ESTADOS_CON_RECIBO,
        })
    return api_ok(data, total=len(data))

@bp.route("/api/v1/pedidos/<int:pedido_id>", methods=["GET"])
@api_requiere_rol("CLIENTE")
def api_pedido_detalle(pedido_id):
    cabecera, detalles = _pedido_del_cliente(pedido_id)
    return api_ok(pedido_json(cabecera) | {"detalles": [detalle_json(d) for d in detalles]})

@bp.route("/api/v1/pedidos/<int:pedido_id>/pago", methods=["POST"])
@api_requiere_rol("CLIENTE")
def api_pagar_pedido(pedido_id):
    """Body: {tipo_pago, numero_tarjeta, fecha_expiracion, cvv, banco, numero_referencia}"""
    datos = cuerpo_json()
    tipo_pago = a_texto(datos.get("tipo_pago"))
    campos = {c: a_texto(datos.get(c)) for c in
              ("numero_tarjeta", "fecha_expiracion", "cvv", "banco", "numero_referencia")}
    servicio = PaymentService()
    try:
        dto = servicio.preparar_pago(pedido_id, tipo_pago, cliente_id=usuario_actual()["id"], **campos)
        resultado = servicio.procesar_pago(pedido_id, dto)
    except PaymentError as e:
        # 402 = el medio de pago fue rechazado; 400/403/404 = datos o pedido inválidos
        defecto = 402 if e.codigo else 400
        raise ApiError(str(e), estado_http(str(e), defecto), codigo=e.codigo)
    return api_ok({"pedido_id": pedido_id, "estado": "PAGADO", "tipo_pago": tipo_pago,
                   "id_transaccion": resultado["id_transaccion"],
                   "redirect": f"/cliente/pedido/{pedido_id}/recibo"},
                  f"¡Pago aprobado! Transacción {resultado['id_transaccion']}.", 201)

@bp.route("/api/v1/pedidos/<int:pedido_id>/recibo", methods=["GET"])
@api_requiere_rol("CLIENTE")
def api_recibo(pedido_id):
    cabecera, _ = _pedido_del_cliente(pedido_id)
    recibo = PaymentService().obtener_recibo(pedido_id)
    return api_ok({"pedido_id": pedido_id, "estado": cabecera["estado"],
                   "recibo": recibo, "disponible": recibo is not None})

@bp.route("/api/v1/pedidos/<int:pedido_id>/recepcion", methods=["POST"])
@api_requiere_rol("CLIENTE")
def api_confirmar_recepcion(pedido_id):
    try:
        resultado = OrderService().confirmar_recepcion(pedido_id, usuario_actual()["id"])
    except OrderError as e:
        raise ApiError(str(e), estado_http(str(e), 409))
    return api_ok({"pedido_id": pedido_id, "estado": resultado.get("estado", "COMPLETADO")},
                  "Recepción confirmada. ¡Buen provecho!")

@bp.route("/api/v1/pedidos/<int:pedido_id>/calificacion", methods=["POST"])
@api_requiere_rol("CLIENTE")
def api_calificar(pedido_id):
    datos = cuerpo_json()
    puntuacion = a_entero(datos.get("puntuacion"), "puntuacion", defecto=5)
    try:
        ReviewService().calificar_pedido(pedido_id, usuario_actual()["id"], puntuacion,
                                         a_texto(datos.get("comentario")))
    except ReviewError as e:
        raise ApiError(str(e), estado_http(str(e), 409))
    return api_ok({"pedido_id": pedido_id, "puntuacion": puntuacion}, "¡Gracias por tu calificación!", 201)
