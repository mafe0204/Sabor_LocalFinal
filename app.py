"""Punto de entrada de SaborLocal. Registra los controladores MVC."""
from controllers.common import app
from controllers.pages_controller import bp as pages_bp
from controllers.auth_controller import bp as auth_bp
from controllers.restaurant_controller import bp as restaurant_bp
from controllers.order_controller import bp as order_bp
from controllers.chef_controller import bp as chef_bp

app.register_blueprint(pages_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(restaurant_bp)
app.register_blueprint(order_bp)
app.register_blueprint(chef_bp)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
