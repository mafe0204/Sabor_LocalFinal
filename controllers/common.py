"""Controlador principal: rutas web (HTML) y endpoints REST (JSON).

La lógica de negocio se delega a services/ y la persistencia a core/database.py.
"""
import functools
import os

from core.mongo_local import preparar_entorno

preparar_entorno()  # enciende la base MongoDB propia (puerto 27018) antes de importar la capa de datos

from pymongo.errors import OperationFailure
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

from core.dtos import UserRegistrationDTO, ChefRegistrationDTO
from services.auth_service import AuthService, AuthError
from services.restaurant_service import RestaurantService, RestaurantError
from services.order_service import OrderService, OrderError
from services.payment_service import PaymentService, PaymentError
from services.review_service import ReviewService, ReviewError

app = Flask(__name__)
app.secret_key = os.environ.get("SABORLOCAL_SECRET", "saborlocal-web-dev-secret")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False  # tildes y ñ legibles en el Response del Network

ESTADOS_LEGIBLES = {
    "PENDIENTE_CHEF": ("Esperando confirmación del restaurante", "warning"),
    "RECHAZADO": ("Rechazado por el restaurante", "danger"),
    "PAGADO": ("Pagado — en cola de preparación", "info"),
    "EN_PREPARACION": ("En preparación", "info"),
    "EN_TRANSITO": ("En camino", "info"),
    "LISTO_PARA_RECOGER": ("Listo para recoger", "info"),
    "COMPLETADO": ("Completado", "success"),
}
ESTADOS_CON_RECIBO = ("PAGADO", "EN_PREPARACION", "EN_TRANSITO", "LISTO_PARA_RECOGER", "COMPLETADO")


# =====================================================================
# Sesión y autorización
# =====================================================================


def usuario_actual():
    return session.get("usuario")

def cantidad_en_carrito(producto_id):
    return sum(i["cantidad"] for i in session.get("carrito", []) if i["producto_id"] == producto_id)

@app.context_processor
def inyectar_globales():
    return {"usuario": usuario_actual()}

def requiere_login(rol=None):
    """Para PÁGINAS HTML: si no hay sesión, redirige al login."""
    def decorador(vista):
        @functools.wraps(vista)
        def envoltura(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                flash("Debes iniciar sesión para continuar.", "warning")
                return redirect(url_for("pages.login"))
            if rol and usuario["rol"] != rol:
                flash("No tienes permiso para acceder a esa sección.", "danger")
                return redirect(url_for("pages.index"))
            return vista(*args, **kwargs)
        return envoltura
    return decorador

class ApiError(Exception):
    def __init__(self, mensaje, estado=400, **extra):
        super().__init__(mensaje)
        self.mensaje, self.estado, self.extra = mensaje, estado, extra

def api_error(mensaje, estado, **extra):
    return jsonify({"ok": False, "error": mensaje, **extra}), estado

def api_ok(data=None, mensaje=None, estado=200, **extra):
    cuerpo = {"ok": True}
    if mensaje:
        cuerpo["message"] = mensaje
    if data is not None:
        cuerpo["data"] = data
    cuerpo.update(extra)
    return jsonify(cuerpo), estado

def estado_http(mensaje, defecto):
    """Elige un código HTTP razonable según el texto del error del servicio."""
    m = (mensaje or "").lower()
    if "no encontrad" in m:
        return 404
    if "no autorizad" in m or "no pertenece" in m or "no tienes permiso" in m:
        return 403
    return defecto

def cuerpo_json():
    datos = request.get_json(silent=True)
    if datos is None:
        return {}
    if not isinstance(datos, dict):
        raise ApiError("El cuerpo debe ser un objeto JSON.", 400)
    return datos

def a_texto(valor):
    return "" if valor is None else str(valor)

def a_entero(valor, campo, defecto=None):
    if valor in (None, ""):
        if defecto is not None:
            return defecto
        raise ApiError(f"El campo '{campo}' es obligatorio.", 400)
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ApiError(f"El campo '{campo}' debe ser un número entero.", 400)

def a_decimal(valor, campo):
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise ApiError(f"El campo '{campo}' debe ser numérico.", 400)

def api_requiere_rol(rol=None):
    """Para la API: sin HTML ni redirecciones, solo JSON con 401 / 403."""
    def decorador(vista):
        @functools.wraps(vista)
        def envoltura(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                return api_error("Autenticación requerida", 401)
            if rol and usuario.get("rol") != rol:
                return api_error("No autorizado", 403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador

@app.before_request
def exigir_json_en_api():
    """Protección CSRF simple: las escrituras de la API solo se aceptan como application/json."""
    if request.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if not request.is_json:
            return api_error("Content-Type debe ser application/json.", 415)

@app.errorhandler(ApiError)
def _manejar_api_error(e):
    return api_error(e.mensaje, e.estado, **e.extra)

@app.errorhandler(404)
def _no_encontrado(e):
    if request.path.startswith("/api/"):
        return api_error("Ruta no encontrada", 404)
    return e

@app.errorhandler(405)
def _metodo_no_permitido(e):
    if request.path.startswith("/api/"):
        return api_error("Método no permitido para esta ruta", 405)
    return e

@app.errorhandler(RuntimeError)
def _sin_base_de_datos(e):
    """Si MongoDB no está encendido, explica el problema en vez de un 500 genérico."""
    if not str(e).startswith("No se pudo conectar a MongoDB"):
        raise e
    if request.path.startswith("/api/"):
        return api_error(str(e), 503)
    return ("<h1>No hay conexión con MongoDB</h1><p>" + str(e) + "</p>", 503)

@app.errorhandler(OperationFailure)
def _bd_pide_autenticacion(e):
    if getattr(e, "code", None) != 13:
        raise e
    mensaje = ("Esa instancia de MongoDB exige usuario y contraseña. Quita la variable MONGO_URI para usar la "
               "base propia de SaborLocal (puerto 27018) o incluye usuario y contraseña en MONGO_URI.")
    if request.path.startswith("/api/"):
        return api_error(mensaje, 503)
    return ("<h1>MongoDB exige autenticación</h1><p>" + mensaje + "</p>", 503)

@app.errorhandler(500)
def _error_interno(e):
    if request.path.startswith("/api/"):
        return api_error("Error interno del servidor", 500)
    return e

def restaurante_json(r):
    claves = ("id", "nombre_restaurante", "direccion", "descripcion", "estado",
              "hora_apertura", "hora_cierre", "en_horario")
    return {k: r.get(k) for k in claves if k in r}

def producto_json(p):
    claves = ("id", "restaurante_id", "nombre", "descripcion", "precio", "inventario", "esta_activo")
    return {k: p.get(k) for k in claves if k in p}

def pedido_json(p):
    legible, clase = ESTADOS_LEGIBLES.get(p.get("estado"), (p.get("estado"), "secondary"))
    claves = ("id", "restaurante_id", "cliente_id", "nombre_restaurante", "estado", "tipo_entrega",
              "direccion_entrega", "subtotal", "monto_comision", "monto_total", "fecha_creacion")
    datos = {k: p.get(k) for k in claves if k in p}
    datos["estado_legible"], datos["estado_clase"] = legible, clase
    return datos

def detalle_json(d):
    return {k: d.get(k) for k in ("producto_id", "nombre", "cantidad", "precio_unitario", "subtotal")}

def carrito_json():
    items = session.get("carrito", [])
    filas = [{**i, "subtotal": round(i["precio"] * i["cantidad"], 2)} for i in items]
    return {
        "items": filas,
        "restaurante_id": items[0]["restaurante_id"] if items else None,
        "cantidad_items": sum(i["cantidad"] for i in items),
        "total": round(sum(f["subtotal"] for f in filas), 2),
    }

def _restaurante_publicado(restaurante_id):
    return next((r for r in RestaurantService().listar_restaurantes_publicados()
                 if r["id"] == restaurante_id), None)

def _pedido_del_cliente(pedido_id):
    try:
        cabecera, detalles = OrderService().detalle_pedido(pedido_id)
    except (OrderError, KeyError):
        cabecera, detalles = None, []
    if not cabecera:
        raise ApiError("Pedido no encontrado.", 404)
    if cabecera["cliente_id"] != usuario_actual()["id"]:
        raise ApiError("Este pedido no te pertenece.", 403)
    return cabecera, detalles

def _restaurante_del_chef():
    restaurante = RestaurantService().obtener_restaurante_por_usuario(usuario_actual()["id"])
    if restaurante is None:
        raise ApiError("No tienes un restaurante asociado.", 404)
    return restaurante

def _borrador():
    return session.get("borrador_platillos", [])

def _borrador_json():
    return [dict(p, indice=i) for i, p in enumerate(_borrador())]

def _datos_perfil(datos):
    return (a_texto(datos.get("nombre_restaurante")), a_texto(datos.get("direccion")),
            a_texto(datos.get("descripcion")), a_texto(datos.get("hora_apertura")),
            a_texto(datos.get("hora_cierre")))

def _datos_platillo(datos, clave_nombre="nombre", clave_desc="descripcion"):
    nombre = a_texto(datos.get(clave_nombre))
    precio = a_decimal(datos.get("precio"), "precio")
    inventario = a_entero(datos.get("inventario"), "inventario")
    if precio <= 0:
        raise ApiError("El precio debe ser mayor a 0.", 400)
    if inventario < 0:
        raise ApiError("El inventario no puede ser negativo.", 400)
    return nombre, a_texto(datos.get(clave_desc)), precio, inventario

def _acciones_chef(pedido, aceptado):
    base = f"/api/v1/chef/pedidos/{pedido['id']}"
    estado = pedido["estado"]
    if estado == "PENDIENTE_CHEF" and not aceptado:
        return [{"accion": "aceptar", "etiqueta": "Aceptar", "metodo": "POST", "url": f"{base}/aceptar"},
                {"accion": "rechazar", "etiqueta": "Rechazar", "metodo": "POST", "url": f"{base}/rechazar"}]
    if estado == "PAGADO":
        return [{"accion": "preparar", "etiqueta": "Iniciar preparación", "metodo": "POST", "url": f"{base}/preparacion"}]
    if estado == "EN_PREPARACION":
        etiqueta = "Despachar" if pedido["tipo_entrega"] == "DOMICILIO" else "Marcar listo para recoger"
        return [{"accion": "despachar", "etiqueta": etiqueta, "metodo": "POST", "url": f"{base}/despacho"}]
    return []

def _accion_de_chef(pedido_id, ejecutar, mensaje, estado_nuevo=None):
    try:
        resultado = ejecutar(OrderService(), pedido_id, usuario_actual()["id"])
    except OrderError as e:
        raise ApiError(str(e), estado_http(str(e), 409))
    msg = resultado.get("mensaje") if isinstance(resultado, dict) and resultado.get("mensaje") else mensaje
    estado = (resultado.get("estado") if isinstance(resultado, dict) else None) or estado_nuevo
    return api_ok({"pedido_id": pedido_id, "estado": estado}, msg)
