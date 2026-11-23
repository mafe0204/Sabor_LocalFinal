"""Controlador de chef."""
from flask import Blueprint
from controllers.common import *
from controllers import common as _common

# Helpers privados compartidos (los nombres con _ no se importan con *)
from controllers.common import _manejar_api_error, _no_encontrado, _metodo_no_permitido, _sin_base_de_datos, _bd_pide_autenticacion, _error_interno, _restaurante_publicado, _pedido_del_cliente, _restaurante_del_chef, _borrador, _borrador_json, _datos_perfil, _datos_platillo, _acciones_chef, _accion_de_chef

bp = Blueprint("chef", __name__)

@bp.route("/api/v1/chef/restaurante", methods=["GET"])
@api_requiere_rol("CHEF")
def api_chef_restaurante():
    servicio = RestaurantService()
    restaurante = servicio.obtener_restaurante_por_usuario(usuario_actual()["id"])
    publicado = bool(restaurante and restaurante["estado"] == "PUBLICADO")
    return api_ok({
        "restaurante": restaurante_json(restaurante) if restaurante else None,
        "borrador_platillos": [] if publicado else _borrador_json(),
        "menu_publicado": [producto_json(p) for p in servicio.listar_productos(restaurante["id"])] if publicado else [],
    })

@bp.route("/api/v1/chef/restaurante", methods=["PUT"])
@api_requiere_rol("CHEF")
def api_chef_actualizar_perfil():
    """Edita el perfil de un restaurante YA publicado."""
    _restaurante_del_chef()
    try:
        RestaurantService().actualizar_perfil(usuario_actual()["id"], *_datos_perfil(cuerpo_json()))
    except RestaurantError as e:
        raise ApiError(str(e), 400)
    return api_ok(restaurante_json(_restaurante_del_chef()), "Perfil del restaurante actualizado.")

@bp.route("/api/v1/chef/restaurante/publicacion", methods=["POST"])
@api_requiere_rol("CHEF")
def api_chef_publicar():
    """Guarda el perfil + los platillos del borrador y publica el restaurante."""
    restaurante = _restaurante_del_chef()
    if restaurante["estado"] == "PUBLICADO":
        raise ApiError("El restaurante ya está publicado.", 409)
    nombre, direccion, descripcion, apertura, cierre = _datos_perfil(cuerpo_json())
    try:
        RestaurantService().configurar_perfil_y_menu(
            usuario_id=usuario_actual()["id"], nombre=nombre, direccion=direccion,
            descripcion=descripcion, hora_apertura=apertura, hora_cierre=cierre,
            platillos=_borrador())
    except RestaurantError as e:
        raise ApiError(str(e), 400)
    session["borrador_platillos"] = []
    return api_ok({"restaurante": restaurante_json(_restaurante_del_chef()), "redirect": "/chef"},
                  "¡Restaurante publicado! Ya aparece en el catálogo de clientes.", 201)

@bp.route("/api/v1/chef/borrador/platillos", methods=["POST"])
@api_requiere_rol("CHEF")
def api_chef_borrador_agregar():
    """Agrega un platillo a la lista (aún sin publicar)."""
    if _restaurante_del_chef()["estado"] == "PUBLICADO":
        raise ApiError("El restaurante ya está publicado; agrega el platillo directamente al menú.", 409)
    nombre, descripcion, precio, inventario = _datos_platillo(cuerpo_json(), "nombre", "descripcion")
    if not nombre.strip():
        raise ApiError("El nombre del platillo es obligatorio.", 400)
    borrador = _borrador()
    borrador.append({"nombre": nombre, "descripcion": descripcion, "precio": precio, "inventario": inventario})
    session["borrador_platillos"] = borrador
    return api_ok(_borrador_json(), "Platillo agregado a la lista (aún no publicado).", 201, total=len(borrador))

@bp.route("/api/v1/chef/borrador/platillos/<int:indice>", methods=["DELETE"])
@api_requiere_rol("CHEF")
def api_chef_borrador_quitar(indice):
    borrador = _borrador()
    if not 0 <= indice < len(borrador):
        raise ApiError("Ese platillo no está en la lista.", 404)
    quitado = borrador.pop(indice)
    session["borrador_platillos"] = borrador
    return api_ok(_borrador_json(), f"'{quitado['nombre']}' quitado de la lista.", total=len(borrador))

@bp.route("/api/v1/chef/menu", methods=["POST"])
@api_requiere_rol("CHEF")
def api_chef_menu_agregar():
    """Agrega un platillo directamente al menú de un restaurante ya publicado."""
    if _restaurante_del_chef()["estado"] != "PUBLICADO":
        raise ApiError("Publica el restaurante antes de agregar platillos directamente al menú.", 409)
    nombre, descripcion, precio, inventario = _datos_platillo(cuerpo_json(), "nombre", "descripcion")
    try:
        producto_id = RestaurantService().agregar_platillo(usuario_actual()["id"], nombre, descripcion, precio, inventario)
    except RestaurantError as e:
        raise ApiError(str(e), 400)
    return api_ok({"id": producto_id, "nombre": nombre.strip(), "precio": precio, "inventario": inventario},
                  "Platillo agregado al menú publicado.", 201)

@bp.route("/api/v1/chef/menu/<int:producto_id>", methods=["GET"])
@api_requiere_rol("CHEF")
def api_chef_menu_detalle(producto_id):
    try:
        producto = RestaurantService().obtener_producto_de_chef(producto_id, usuario_actual()["id"])
    except RestaurantError as e:
        raise ApiError(str(e), 404)
    return api_ok(producto_json(producto))

@bp.route("/api/v1/chef/menu/<int:producto_id>", methods=["PUT"])
@api_requiere_rol("CHEF")
def api_chef_menu_actualizar(producto_id):
    nombre, descripcion, precio, inventario = _datos_platillo(cuerpo_json(), "nombre", "descripcion")
    try:
        RestaurantService().actualizar_producto(producto_id=producto_id, usuario_id=usuario_actual()["id"],
                                                nombre=nombre, descripcion=descripcion,
                                                precio=precio, inventario=inventario)
    except RestaurantError as e:
        raise ApiError(str(e), estado_http(str(e), 400))
    return api_ok({"id": producto_id, "nombre": nombre.strip(), "descripcion": descripcion,
                   "precio": precio, "inventario": inventario, "redirect": "/chef/menu"},
                  "Platillo actualizado.")

@bp.route("/api/v1/chef/pedidos", methods=["GET"])
@api_requiere_rol("CHEF")
def api_chef_pedidos():
    restaurante = RestaurantService().obtener_restaurante_por_usuario(usuario_actual()["id"])
    data = []
    if restaurante and restaurante["estado"] == "PUBLICADO":
        ordenes = OrderService()
        for p in ordenes.listar_pedidos_de_chef(restaurante["id"]):
            aceptado = ordenes.pedido_fue_aceptado(p["id"])
            data.append(pedido_json(p) | {
                "aceptado_por_chef": aceptado,
                "detalles": [detalle_json(d) for d in ordenes.detalle_pedido(p["id"])[1]],
                "acciones": _acciones_chef(p, aceptado),
            })
    return api_ok(data, restaurante=restaurante_json(restaurante) if restaurante else None, total=len(data))

@bp.route("/api/v1/chef/pedidos/<int:pedido_id>/aceptar", methods=["POST"])
@api_requiere_rol("CHEF")
def api_chef_aceptar(pedido_id):
    return _accion_de_chef(pedido_id, lambda s, p, c: s.aceptar_pedido(p, c),
                           "Pedido aceptado. El cliente ya puede pagar.", "PENDIENTE_CHEF")

@bp.route("/api/v1/chef/pedidos/<int:pedido_id>/rechazar", methods=["POST"])
@api_requiere_rol("CHEF")
def api_chef_rechazar(pedido_id):
    motivo = a_texto(cuerpo_json().get("motivo"))
    return _accion_de_chef(pedido_id, lambda s, p, c: s.rechazar_pedido(p, c, motivo),
                           "Pedido rechazado. Se devolvió el stock reservado.", "RECHAZADO")

@bp.route("/api/v1/chef/pedidos/<int:pedido_id>/preparacion", methods=["POST"])
@api_requiere_rol("CHEF")
def api_chef_preparar(pedido_id):
    return _accion_de_chef(pedido_id, lambda s, p, c: s.iniciar_preparacion_comando(p, c),
                           "Preparación iniciada.", "EN_PREPARACION")

@bp.route("/api/v1/chef/pedidos/<int:pedido_id>/despacho", methods=["POST"])
@api_requiere_rol("CHEF")
def api_chef_despachar(pedido_id):
    return _accion_de_chef(pedido_id, lambda s, p, c: s.despachar_o_marcar_listo(p, c), "Pedido despachado.")
