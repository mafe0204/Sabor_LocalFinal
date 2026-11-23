import glob
import os
import re
import shutil
import socket
import subprocess
import time

PUERTO = int(os.environ.get("SABORLOCAL_MONGO_PUERTO", "27018"))


def carpeta_datos():
    """Carpeta de datos. En Windows va en AppData (ruta sin tildes ni ñ, que mongod maneja mejor)."""
    if os.environ.get("SABORLOCAL_DATOS"):
        return os.environ["SABORLOCAL_DATOS"]
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return os.path.join(os.environ["LOCALAPPDATA"], "SaborLocal", "datos_mongo")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos_mongo")


def puerto_abierto(puerto=PUERTO, espera=0.5):
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=espera):
            return True
    except OSError:
        return False


def buscar_mongod():
    ruta = shutil.which("mongod")
    if ruta:
        return ruta
    candidatos = []
    for patron in (r"C:\Program Files\MongoDB\Server\*\bin\mongod.exe",
                   r"C:\Program Files (x86)\MongoDB\Server\*\bin\mongod.exe",
                   "/opt/homebrew/bin/mongod", "/usr/local/bin/mongod", "/usr/bin/mongod"):
        candidatos += glob.glob(patron)
    if not candidatos:
        return None

    def version(r):
        m = re.search(r"Server[\\/]([\d.]+)", r)
        return tuple(int(x) for x in m.group(1).split(".") if x) if m else (0,)
    return sorted(candidatos, key=version, reverse=True)[0]


def _iniciar(mongod, datos):
    os.makedirs(datos, exist_ok=True)
    opciones = {}
    if os.name == "nt":
        opciones["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        opciones["start_new_session"] = True
    log = open(os.path.join(datos, "mongod.log"), "ab")
    subprocess.Popen([mongod, "--dbpath", datos, "--port", str(PUERTO), "--bind_ip", "127.0.0.1"],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, **opciones)
    for _ in range(60):
        time.sleep(0.5)
        if puerto_abierto():
            return True
    return False


def preparar_entorno():
    if os.environ.get("SABORLOCAL_MOCK") == "1" or os.environ.get("MONGO_URI"):
        return  # el usuario eligió modo demo o su propia conexión
    os.environ["MONGO_URI"] = f"mongodb://127.0.0.1:{PUERTO}"

    if puerto_abierto():
        print(f"[SaborLocal] Usando la base de datos propia en el puerto {PUERTO}.")
        return
    mongod = buscar_mongod()
    if mongod is None:
        print("[SaborLocal] AVISO: no encontré MongoDB instalado. Abro en MODO DEMO (datos en memoria, se borran al cerrar).")
        os.environ.pop("MONGO_URI", None)
        os.environ["SABORLOCAL_MOCK"] = "1"
        return
    datos = carpeta_datos()
    print(f"[SaborLocal] Encendiendo base de datos propia en el puerto {PUERTO} (datos en: {datos}) ...")
    if _iniciar(mongod, datos):
        print("[SaborLocal] Base de datos lista: saborlocal_web")
    else:
        print(f"[SaborLocal] AVISO: mongod no arrancó (revisa {os.path.join(datos, 'mongod.log')}). Abro en MODO DEMO.")
        os.environ.pop("MONGO_URI", None)
        os.environ["SABORLOCAL_MOCK"] = "1"
