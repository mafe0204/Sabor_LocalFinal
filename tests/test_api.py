import os
import unittest

os.environ["SABORLOCAL_MOCK"] = "1"

from app import app  # noqa: E402


def post(c, url, cuerpo=None):
    return c.post(url, json=cuerpo if cuerpo is not None else {})


class FlujoCompleto(unittest.TestCase):
    def test_flujo(self):
        chef, cli = app.test_client(), app.test_client()

        # --- registro y login
        r = post(chef, "/api/v1/auth/registro/chef", {"nombre": "Ana Chef", "correo": "ana@x.co", "contrasena": "1234",
                 "nombre_restaurante": "La Casa", "direccion": "Calle 1", "descripcion": "Casera"})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(post(chef, "/api/v1/auth/registro/chef", {"nombre": "Ana", "correo": "ana@x.co",
                 "contrasena": "1234", "nombre_restaurante": "X", "direccion": "Y"}).status_code, 409)
        self.assertEqual(post(chef, "/api/v1/auth/login", {"correo": "ana@x.co", "contrasena": "mala"}).status_code, 401)
        r = post(chef, "/api/v1/auth/login", {"correo": "ana@x.co", "contrasena": "1234"})
        self.assertEqual(r.json["data"]["redirect"], "/chef")

        # --- chef: borrador -> publicar
        r = post(chef, "/api/v1/chef/borrador/platillos", {"nombre": "Bandeja", "descripcion": "paisa", "precio": "25000", "inventario": "5"})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(r.json["data"][0]["indice"], 0)
        self.assertEqual(post(chef, "/api/v1/chef/borrador/platillos", {"nombre": "X", "precio": "-1", "inventario": "1"}).status_code, 400)
        r = post(chef, "/api/v1/chef/restaurante/publicacion", {"nombre_restaurante": "La Casa", "direccion": "Calle 1",
                 "descripcion": "Casera", "hora_apertura": "00:00", "hora_cierre": "23:59"})
        self.assertEqual(r.status_code, 201, r.json)
        r = chef.get("/api/v1/chef/restaurante")
        self.assertEqual(r.json["data"]["restaurante"]["estado"], "PUBLICADO")
        pid = r.json["data"]["menu_publicado"][0]["id"]
        rid = r.json["data"]["restaurante"]["id"]

        # editar y agregar en menú publicado
        r = chef.put(f"/api/v1/chef/menu/{pid}", json={"nombre": "Bandeja paisa", "descripcion": "", "precio": 26000, "inventario": 5})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(post(chef, "/api/v1/chef/menu", {"nombre": "Jugo", "descripcion": "", "precio": 5000, "inventario": 3}).status_code, 201)

        # --- cliente
        post(cli, "/api/v1/auth/registro/cliente", {"nombre": "Luis", "correo": "luis@x.co", "contrasena": "1234"})
        self.assertEqual(cli.get("/api/v1/carrito").status_code, 401)
        post(cli, "/api/v1/auth/login", {"correo": "luis@x.co", "contrasena": "1234"})
        self.assertEqual(chef.get("/api/v1/carrito").status_code, 403)

        r = cli.get("/api/v1/restaurantes")
        self.assertEqual(r.json["total"], 1)
        r = cli.get(f"/api/v1/restaurantes/{rid}/menu")
        self.assertEqual(r.json["total"], 2)

        r = post(cli, "/api/v1/carrito/items", {"restaurante_id": rid, "producto_id": pid, "cantidad": 2})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(r.json["data"]["total"], 52000)
        r = post(cli, "/api/v1/carrito/items", {"restaurante_id": rid, "producto_id": pid, "cantidad": 99})
        self.assertEqual(r.json["level"], "warning")           # se limita al stock
        r = cli.patch(f"/api/v1/carrito/items/{pid}", json={"cantidad": 2})
        self.assertEqual(r.json["data"]["cantidad_items"], 2)

        # domicilio sin dirección -> 400
        self.assertEqual(post(cli, "/api/v1/pedidos", {"tipo_entrega": "DOMICILIO", "direccion": ""}).status_code, 400)
        r = post(cli, "/api/v1/pedidos", {"tipo_entrega": "DOMICILIO", "direccion": "Calle 5 # 10-20"})
        self.assertEqual(r.status_code, 201, r.json)
        oid = r.json["data"]["pedido_id"]
        self.assertEqual(cli.get("/api/v1/carrito").json["data"]["items"], [])

        # no se puede pagar antes de que el chef acepte
        r = post(cli, f"/api/v1/pedidos/{oid}/pago", {"tipo_pago": "TARJETA_CREDITO", "numero_tarjeta": "4111111111111111",
                 "fecha_expiracion": "12/30", "cvv": "123"})
        self.assertIn(r.status_code, (400, 409), r.json)

        # --- chef acepta
        r = chef.get("/api/v1/chef/pedidos")
        self.assertEqual([a["accion"] for a in r.json["data"][0]["acciones"]], ["aceptar", "rechazar"])
        self.assertEqual(post(chef, f"/api/v1/chef/pedidos/{oid}/aceptar").status_code, 200)

        # --- pago rechazado (0000) y luego aprobado
        r = post(cli, f"/api/v1/pedidos/{oid}/pago", {"tipo_pago": "TARJETA_CREDITO", "numero_tarjeta": "4000000000000000",
                 "fecha_expiracion": "12/30", "cvv": "123"})
        self.assertEqual(r.status_code, 402, r.json)
        self.assertEqual(r.json["codigo"], "INSUFFICIENT_FUNDS")
        r = post(cli, f"/api/v1/pedidos/{oid}/pago", {"tipo_pago": "TRANSFERENCIA", "banco": "Banco de Bogotá", "numero_referencia": "123456"})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertTrue(r.json["data"]["id_transaccion"].startswith("TXN-"))
        r = cli.get(f"/api/v1/pedidos/{oid}/recibo")
        self.assertTrue(r.json["data"]["disponible"])
        self.assertIn("RECIBO DE COMPRA", r.json["data"]["recibo"])

        # --- chef prepara y despacha, cliente confirma y califica
        self.assertEqual(post(chef, f"/api/v1/chef/pedidos/{oid}/preparacion").status_code, 200)
        self.assertEqual(post(chef, f"/api/v1/chef/pedidos/{oid}/despacho").status_code, 200)
        lista = cli.get("/api/v1/pedidos").json["data"]
        self.assertTrue(lista[0]["puede_confirmar"])
        self.assertEqual(post(cli, f"/api/v1/pedidos/{oid}/recepcion").status_code, 200)
        self.assertEqual(post(cli, f"/api/v1/pedidos/{oid}/calificacion", {"puntuacion": 5, "comentario": "Rico"}).status_code, 201)
        self.assertEqual(post(cli, f"/api/v1/pedidos/{oid}/calificacion", {"puntuacion": 4}).status_code, 409)

        # --- chef retira platillo (endpoint existente)
        self.assertEqual(chef.delete(f"/api/v1/restaurantes/{rid}/menu/{pid}", json={}).status_code, 200)

        # --- seguridad / formato
        self.assertEqual(cli.post("/api/v1/carrito/items", data="a=1").status_code, 415)
        self.assertEqual(cli.get("/api/v1/no-existe").status_code, 404)
        self.assertEqual(post(cli, "/api/v1/auth/logout").status_code, 200)
        self.assertEqual(cli.get("/api/v1/auth/me").status_code, 401)

    def test_paginas_html(self):
        c = app.test_client()
        self.assertEqual(c.get("/login").status_code, 200)
        self.assertEqual(c.get("/cliente").status_code, 302)   # sin sesión -> login
        html = c.get("/registro/chef").get_data(as_text=True)
        self.assertIn('data-page="registro_chef"', html)
        self.assertIn("static/js/app.js", html)


if __name__ == "__main__":
    unittest.main()
