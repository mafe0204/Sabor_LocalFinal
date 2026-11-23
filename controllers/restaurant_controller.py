"""Controlador de restaurant."""
from flask import Blueprint
from controllers.common import *
from controllers import common as _common

# Helpers privados compartidos (los nombres con _ no se importan con *)
from controllers.common import _manejar_api_error, _no_encontrado, _metodo_no_permitido, _sin_base_de_datos, _bd_pide_autenticacion, _error_interno, _restaurante_publicado, _pedido_del_cliente, _restaurante_del_chef, _borrador, _borrador_json, _datos_perfil, _datos_platillo, _acciones_chef, _accion_de_chef

bp = Blueprint("restaurant", __name__)

@bp.route("/api/v1/restaurantes", methods=["GET"])
def api_restaurantes():
    restaurantes = RestaurantService().listar_restaurantes_publicados()
    return api_ok([restaurante_json(r) for r in restaurantes], total=len(restaurantes))

@bp.route("/api/v1/restaurantes/<int:restaurante_id>", methods=["GET"])
def api_restaurante(restaurante_id):
    restaurante = _restaurante_publicado(restaurante_id)
    if restaurante is None:
        raise ApiError("Restaurante no encontrado", 404)
    return api_ok(restaurante_json(restaurante))

@bp.route("/api/v1/restaurantes/<int:restaurante_id>/menu", methods=["GET"])
def api_menu_restaurante(restaurante_id):
    restaurante = _restaurante_publicado(restaurante_id)
    if restaurante is None:
        raise ApiError("Restaurante no encontrado", 404)
    productos = RestaurantService().listar_productos(restaurante_id)
    data = []
    for p in productos:
        en_carrito = cantidad_en_carrito(p["id"])
        data.append(producto_json(p) | {"en_carrito": en_carrito, "quedan": p["inventario"] - en_carrito})
    return api_ok(data, restaurante={"id": restaurante["id"], "nombre": restaurante["nombre_restaurante"],
                                      "direccion": restaurante.get("direccion"),
                                      "en_horario": restaurante.get("en_horario")},
                  total=len(data))

@bp.route("/api/v1/restaurantes/<int:restaurante_id>/menu/<int:producto_id>", methods=["GET"])
def api_producto_menu(restaurante_id, producto_id):
    if _restaurante_publicado(restaurante_id) is None:
        raise ApiError("Restaurante no encontrado", 404)
    producto = RestaurantService().obtener_producto(producto_id)
    if producto is None or producto.get("restaurante_id") != restaurante_id:
        raise ApiError("Platillo no encontrado", 404)
    return api_ok(producto_json(producto))

@bp.route("/api/v1/restaurantes/<int:restaurante_id>/menu/<int:producto_id>", methods=["DELETE"])
@api_requiere_rol("CHEF")
def api_quitar_producto(restaurante_id, producto_id):
    servicio = RestaurantService()
    restaurante = servicio.obtener_restaurante_por_usuario(usuario_actual()["id"])
    if restaurante is None or restaurante["id"] != restaurante_id:
        raise ApiError("El restaurante no pertenece al chef autenticado", 403)
    try:
        servicio.quitar_producto(producto_id, usuario_actual()["id"])
    except RestaurantError as e:
        raise ApiError(str(e), 404)
    return api_ok({"restaurante_id": restaurante_id, "producto_id": producto_id, "esta_activo": False},
                  "Platillo retirado del menú")
