"""Controlador de auth."""
from flask import Blueprint
from controllers.common import *
from controllers import common as _common

# Helpers privados compartidos (los nombres con _ no se importan con *)
from controllers.common import _manejar_api_error, _no_encontrado, _metodo_no_permitido, _sin_base_de_datos, _bd_pide_autenticacion, _error_interno, _restaurante_publicado, _pedido_del_cliente, _restaurante_del_chef, _borrador, _borrador_json, _datos_perfil, _datos_platillo, _acciones_chef, _accion_de_chef

bp = Blueprint("auth", __name__)

@bp.route("/api/v1/auth/login", methods=["POST"])
def api_login():
    datos = cuerpo_json()
    try:
        resultado = AuthService().iniciar_sesion(a_texto(datos.get("correo")).strip(), a_texto(datos.get("contrasena")))
    except AuthError as e:
        raise ApiError(str(e), 401)
    session["usuario"] = resultado["usuario"]
    session["token"] = resultado["token"]
    session["carrito"] = []
    destino = "/cliente" if resultado["usuario"]["rol"] == "CLIENTE" else "/chef"
    return api_ok({"usuario": resultado["usuario"], "redirect": destino}, "Sesión iniciada.")

@bp.route("/api/v1/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return api_ok({"redirect": "/login"}, "Sesión cerrada.")

@bp.route("/api/v1/auth/me", methods=["GET"])
@api_requiere_rol()
def api_auth_me():
    return api_ok(usuario_actual())

@bp.route("/api/v1/auth/registro/cliente", methods=["POST"])
def api_registro_cliente():
    datos = cuerpo_json()
    dto = UserRegistrationDTO(
        nombre=a_texto(datos.get("nombre")),
        correo_electronico=a_texto(datos.get("correo")).strip(),
        contrasena=a_texto(datos.get("contrasena")),
    )
    try:
        AuthService().registrar_cliente(dto)
    except AuthError as e:
        raise ApiError(str(e), 409 if "registrado" in str(e) else 400)
    return api_ok({"correo": dto.correo_electronico, "rol": "CLIENTE", "redirect": "/login"},
                  "Cuenta creada. Ahora puedes iniciar sesión.", 201)

@bp.route("/api/v1/auth/registro/chef", methods=["POST"])
def api_registro_chef():
    datos = cuerpo_json()
    dto = ChefRegistrationDTO(
        nombre=a_texto(datos.get("nombre")),
        correo_electronico=a_texto(datos.get("correo")).strip(),
        contrasena=a_texto(datos.get("contrasena")),
        nombre_restaurante=a_texto(datos.get("nombre_restaurante")),
        direccion=a_texto(datos.get("direccion")),
        descripcion=a_texto(datos.get("descripcion")),
    )
    try:
        AuthService().registrar_chef(dto)
    except AuthError as e:
        raise ApiError(str(e), 409 if "registrado" in str(e) else 400)
    return api_ok({"correo": dto.correo_electronico, "rol": "CHEF",
                   "nombre_restaurante": dto.nombre_restaurante, "redirect": "/login"},
                  "Restaurante registrado. Inicia sesión para configurar tu menú y publicarlo.", 201)
