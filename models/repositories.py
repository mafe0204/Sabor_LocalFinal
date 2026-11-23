"""Repositorios de persistencia MongoDB usados por la capa de modelo.

Los servicios de services/ contienen las reglas de dominio y utilizan Database;
esta capa ofrece acceso tipado por colección para consultas y operaciones CRUD.
"""
from core.database import get_db

class MongoRepository:
    collection = None
    def __init__(self):
        if not self.collection:
            raise NotImplementedError("Define la colección del repositorio")
        self.db = get_db()
    def listar(self, filtro=None, orden=None):
        return self.db.buscar(self.collection, filtro or {}, orden)
    def obtener(self, filtro):
        return self.db.buscar_uno(self.collection, filtro)
    def crear(self, datos):
        return self.db.insertar(self.collection, datos)
    def actualizar(self, filtro, cambios):
        return self.db.actualizar(self.collection, filtro, cambios)
    def eliminar(self, filtro):
        return self.db.db[self.collection].delete_one(filtro).deleted_count

class UsuarioRepository(MongoRepository): collection = "usuarios"
class RestauranteRepository(MongoRepository): collection = "restaurantes"
class ProductoRepository(MongoRepository): collection = "productos"
class PedidoRepository(MongoRepository): collection = "pedidos"
class PagoRepository(MongoRepository): collection = "pagos"
class CalificacionRepository(MongoRepository): collection = "calificaciones"
