"""Controlador de pages."""
from flask import Blueprint
from controllers.common import *
from controllers import common as _common

# Helpers privados compartidos (los nombres con _ no se importan con *)
from controllers.common import _manejar_api_error, _no_encontrado, _metodo_no_permitido, _sin_base_de_datos, _bd_pide_autenticacion, _error_interno, _restaurante_publicado, _pedido_del_cliente, _restaurante_del_chef, _borrador, _borrador_json, _datos_perfil, _datos_platillo, _acciones_chef, _accion_de_chef

bp = Blueprint("pages", __name__)

@bp.route("/")
def index():
    usuario = usuario_actual()
    if usuario is None:
        return redirect(url_for("pages.login"))
    destino = {"CLIENTE": "pages.panel_cliente", "CHEF": "pages.panel_chef"}
    return redirect(url_for(destino[usuario["rol"]]))

@bp.route("/login")
def login():
    return render_template("login.html")

@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("pages.login"))

@bp.route("/registro/cliente")
def registro_cliente():
    return render_template("registro_cliente.html")

@bp.route("/registro/chef")
def registro_chef():
    return render_template("registro_chef.html")

@bp.route("/cliente")
@requiere_login("CLIENTE")
def panel_cliente():
    return render_template("cliente_explorar.html")

@bp.route("/cliente/restaurante/<int:restaurante_id>")
@requiere_login("CLIENTE")
def cliente_restaurante(restaurante_id):
    return render_template("cliente_menu.html", restaurante_id=restaurante_id)

@bp.route("/cliente/carrito")
@requiere_login("CLIENTE")
def carrito_ver():
    return render_template("cliente_carrito.html")

@bp.route("/cliente/pedidos")
@requiere_login("CLIENTE")
def cliente_pedidos():
    return render_template("cliente_pedidos.html")

@bp.route("/cliente/pedido/<int:pedido_id>/pagar")
@requiere_login("CLIENTE")
def cliente_pagar(pedido_id):
    return render_template("cliente_pagar.html", pedido_id=pedido_id)

@bp.route("/cliente/pedido/<int:pedido_id>/recibo")
@requiere_login("CLIENTE")
def cliente_recibo(pedido_id):
    return render_template("cliente_recibo.html", pedido_id=pedido_id)

@bp.route("/chef")
@requiere_login("CHEF")
def panel_chef():
    return render_template("chef_panel.html")

@bp.route("/chef/menu")
@requiere_login("CHEF")
def chef_menu():
    return render_template("chef_menu.html")

@bp.route("/chef/producto/<int:producto_id>/editar")
@requiere_login("CHEF")
def chef_editar_producto(producto_id):
    return render_template("chef_editar_producto.html", producto_id=producto_id)

@bp.route("/api/v1/clientes/me", methods=["GET"])
@api_requiere_rol("CLIENTE")
def api_cliente_actual():
    u = usuario_actual()
    return api_ok({"id": u["id"], "nombre": u.get("nombre"), "correo": u.get("correo"), "rol": u.get("rol")})
