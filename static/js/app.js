/* SaborLocal — front-end.
 * Cada botón/formulario llama a /api/v1/... con fetch y JSON.
 * Para verlo: F12 > Network > filtro "Fetch/XHR" > clic en la petición > pestañas Payload y Response.
 */
(function () {
  "use strict";

  // ------------------------------------------------------------------ utilidades
  const $ = (sel, raiz) => (raiz || document).querySelector(sel);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const dinero = (n) => "$" + Number(n || 0).toLocaleString("es-CO", { maximumFractionDigits: 0 });

  async function api(metodo, ruta, cuerpo) {
    const opciones = {
      method: metodo,
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      credentials: "same-origin",
    };
    if (metodo !== "GET") opciones.body = JSON.stringify(cuerpo || {});
    let respuesta;
    try {
      respuesta = await fetch("/api/v1" + ruta, opciones);
    } catch (e) {
      throw new Error("No se pudo conectar con el servidor.");
    }
    let json = null;
    try { json = await respuesta.json(); } catch (e) { /* sin cuerpo JSON */ }
    if (respuesta.status === 401 && json && json.error === "Autenticación requerida") {
      location.href = "/login";
      throw new Error(json.error);
    }
    if (!respuesta.ok || !json || json.ok === false) {
      const error = new Error((json && json.error) || "Error inesperado (" + respuesta.status + ")");
      error.estado = respuesta.status;
      error.datos = json;
      throw error;
    }
    return json;
  }

  function aviso(mensaje, nivel) {
    const caja = $("#avisos");
    if (!caja) return;
    caja.innerHTML = '<div class="flash flash-' + esc(nivel || "info") + '">' + esc(mensaje) + "</div>";
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function avisoDespues(mensaje, nivel, destino) {
    try { sessionStorage.setItem("aviso", JSON.stringify([mensaje, nivel || "success"])); } catch (e) { /* ignorar */ }
    location.href = destino;
  }

  function mostrarAvisoGuardado() {
    try {
      const guardado = sessionStorage.getItem("aviso");
      if (guardado) {
        sessionStorage.removeItem("aviso");
        const [m, n] = JSON.parse(guardado);
        aviso(m, n);
      }
    } catch (e) { /* ignorar */ }
  }

  // Ejecuta una acción de la API, muestra el aviso y bloquea el botón mientras espera.
  async function ejecutar(boton, accion) {
    if (boton) boton.disabled = true;
    try {
      return await accion();
    } catch (e) {
      aviso(e.message, e.estado === 409 || e.estado === 400 ? "warning" : "danger");
      return null;
    } finally {
      if (boton) boton.disabled = false;
    }
  }

  const datosForm = (form) => Object.fromEntries(new FormData(form).entries());
  const insignia = (p) => '<span class="badge badge-' + esc(p.estado_clase) + '">' + esc(p.estado_legible) + "</span>";

  // ------------------------------------------------------------------ páginas
  const paginas = {};

  // ---- autenticación
  paginas.login = function () {
    $("#form-login").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const r = await ejecutar($("button[type=submit]", ev.target), () => api("POST", "/auth/login", datosForm(ev.target)));
      if (r) location.href = r.data.redirect;
    });
  };

  paginas.registro_cliente = function () {
    $("#form-registro").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const r = await ejecutar($("button[type=submit]", ev.target), () => api("POST", "/auth/registro/cliente", datosForm(ev.target)));
      if (r) avisoDespues(r.message, "success", r.data.redirect);
    });
  };

  paginas.registro_chef = function () {
    $("#form-registro").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const r = await ejecutar($("button[type=submit]", ev.target), () => api("POST", "/auth/registro/chef", datosForm(ev.target)));
      if (r) avisoDespues(r.message, "success", r.data.redirect);
    });
  };

  // ---- cliente: explorar restaurantes
  paginas.cliente_explorar = async function () {
    const cont = $("#contenido");
    const r = await ejecutar(null, () => api("GET", "/restaurantes"));
    if (!r) { cont.innerHTML = ""; return; }
    if (!r.data.length) { cont.innerHTML = '<p class="muted">Todavía no hay restaurantes publicados.</p>'; return; }
    cont.innerHTML = '<div class="grid">' + r.data.map((x) => (
      '<div class="card"><h3>' + esc(x.nombre_restaurante) + "</h3>" +
      '<p class="muted">' + esc(x.direccion) + "</p><p>" + esc(x.descripcion || "") + "</p><p>" +
      (x.en_horario ? '<span class="badge badge-success">Abierto ahora</span>' : '<span class="badge badge-secondary">Cerrado</span>') +
      (x.hora_apertura ? ' <span class="muted">' + esc(x.hora_apertura) + " - " + esc(x.hora_cierre) + "</span>" : "") +
      '</p><a class="btn" href="/cliente/restaurante/' + x.id + '">Ver menú</a></div>'
    )).join("") + "</div>";
  };

  // ---- cliente: menú de un restaurante
  paginas.cliente_menu = async function (app) {
    const id = app.dataset.restauranteId;
    const cont = $("#contenido");

    async function cargar() {
      const r = await ejecutar(null, () => api("GET", "/restaurantes/" + id + "/menu"));
      if (!r) { cont.innerHTML = '<a href="/cliente">&larr; Volver a restaurantes</a>'; return; }
      const rest = r.restaurante;
      cont.innerHTML =
        '<a href="/cliente">&larr; Volver a restaurantes</a><h1>' + esc(rest.nombre) + "</h1>" +
        '<p class="muted">' + esc(rest.direccion || "") + "</p>" +
        (r.data.length ? '<div class="grid">' + r.data.map(tarjetaProducto).join("") + "</div>"
                       : '<p class="muted">Este restaurante no tiene platillos activos.</p>');
    }

    function tarjetaProducto(p) {
      let accion;
      if (p.quedan > 0) {
        accion = '<form class="f-agregar" data-producto="' + p.id + '">' +
          '<input type="number" name="cantidad" value="1" min="1" max="' + p.quedan + '" style="width:70px;display:inline-block;"> ' +
          '<button type="submit">Agregar +</button></form>';
      } else if (p.inventario > 0) {
        accion = '<button type="button" disabled>Ya tienes todo el stock en tu carrito</button>';
      } else {
        accion = '<button type="button" disabled>Sin stock</button>';
      }
      return '<div class="card"><h3>' + esc(p.nombre) + '</h3><p class="muted">' + esc(p.descripcion || "") + "</p>" +
        "<p><strong>" + dinero(p.precio) + "</strong> — " +
        (p.inventario <= 0 ? '<span class="badge badge-danger">Agotado</span>' : "stock: " + p.inventario) +
        (p.en_carrito ? '<br><span class="muted">En tu carrito: ' + p.en_carrito + "</span>" : "") + "</p>" + accion + "</div>";
    }

    cont.addEventListener("submit", async (ev) => {
      const form = ev.target.closest(".f-agregar");
      if (!form) return;
      ev.preventDefault();
      const r = await ejecutar($("button", form), () => api("POST", "/carrito/items", {
        restaurante_id: Number(id), producto_id: Number(form.dataset.producto), cantidad: Number(form.elements.cantidad.value),
      }));
      if (r) { await cargar(); aviso(r.message, r.level); }
    });
    cargar();
  };

  // ---- cliente: carrito
  paginas.cliente_carrito = async function () {
    const cont = $("#contenido");

    async function cargar() {
      const r = await ejecutar(null, () => api("GET", "/carrito"));
      if (!r) return;
      const c = r.data;
      if (!c.items.length) {
        cont.innerHTML = '<p class="muted">Tu carrito está vacío. <a href="/cliente">Explora restaurantes</a>.</p>';
        return;
      }
      cont.innerHTML =
        '<div class="card">' + c.items.map((i) => (
          '<div class="fila"><span>' + esc(i.nombre) + " — " + dinero(i.precio) + " c/u &nbsp;<strong>Subtotal: " + dinero(i.subtotal) + "</strong></span>" +
          '<div style="display:flex; gap:6px; align-items:center;">' +
          '<form class="f-actualizar" data-producto="' + i.producto_id + '" style="display:flex; gap:6px;">' +
          '<input type="number" name="cantidad" value="' + i.cantidad + '" min="1" style="width:65px;">' +
          '<button type="submit" class="btn-outline">Actualizar</button></form>' +
          '<button type="button" class="btn-secondary b-quitar" data-producto="' + i.producto_id + '">Quitar</button></div></div>'
        )).join("") +
        '<h3 style="text-align:right;">Subtotal: ' + dinero(c.total) + ' <span class="muted">(+10% comisión al confirmar)</span></h3>' +
        '<button type="button" class="btn-outline b-vaciar">Vaciar carrito</button></div>' +
        '<div class="card"><h3>Tipo de entrega</h3><form id="f-checkout">' +
        '<label><input type="radio" name="tipo_entrega" value="DOMICILIO" checked> Domicilio</label> ' +
        '<label><input type="radio" name="tipo_entrega" value="RECOGER"> Recoger en el local</label>' +
        '<div id="dir"><label>Dirección de entrega</label><input type="text" name="direccion" placeholder="Ej: Calle 5 # 10-20"></div>' +
        '<button type="submit">Confirmar pedido</button></form></div>';
    }

    cont.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = ev.target;
      if (f.classList.contains("f-actualizar")) {
        const r = await ejecutar($("button", f), () => api("PATCH", "/carrito/items/" + f.dataset.producto, { cantidad: Number(f.elements.cantidad.value) }));
        if (r) { await cargar(); aviso(r.message, r.level); }
      } else if (f.id === "f-checkout") {
        const d = datosForm(f);
        const r = await ejecutar($("button[type=submit]", f), () => api("POST", "/pedidos", { tipo_entrega: d.tipo_entrega, direccion: d.direccion || "" }));
        if (r) avisoDespues(r.message, "success", r.data.redirect);
      }
    });
    cont.addEventListener("click", async (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      if (b.classList.contains("b-quitar")) {
        const r = await ejecutar(b, () => api("DELETE", "/carrito/items/" + b.dataset.producto));
        if (r) { await cargar(); aviso(r.message, "info"); }
      } else if (b.classList.contains("b-vaciar")) {
        const r = await ejecutar(b, () => api("DELETE", "/carrito"));
        if (r) { await cargar(); aviso(r.message, "info"); }
      }
    });
    cont.addEventListener("change", (ev) => {
      if (ev.target.name === "tipo_entrega") $("#dir").style.display = ev.target.value === "DOMICILIO" ? "block" : "none";
    });
    cargar();
  };

  // ---- cliente: mis pedidos
  paginas.cliente_pedidos = async function () {
    const cont = $("#contenido");

    async function cargar() {
      const r = await ejecutar(null, () => api("GET", "/pedidos"));
      if (!r) return;
      if (!r.data.length) { cont.innerHTML = '<p class="muted">Aún no tienes pedidos.</p>'; return; }
      cont.innerHTML = r.data.map((p) => {
        let acciones = "";
        if (p.puede_pagar) acciones += '<a class="btn" href="/cliente/pedido/' + p.id + '/pagar">Pagar ahora</a>';
        else if (p.estado === "PENDIENTE_CHEF") acciones += '<span class="muted">Esperando que el restaurante confirme el pedido...</span>';
        if (p.puede_confirmar) acciones += '<button type="button" class="btn-verde b-confirmar" data-id="' + p.id + '">Confirmar recibido</button>';
        if (p.puede_calificar) {
          acciones += '<form class="f-calificar" data-id="' + p.id + '" style="display:flex;gap:6px;align-items:center;">' +
            '<select name="puntuacion" style="width:auto;">' + [5, 4, 3, 2, 1].map((n) => '<option value="' + n + '">' + n + " ★</option>").join("") + "</select>" +
            '<input type="text" name="comentario" placeholder="Comentario (opcional)" style="width:180px;">' +
            '<button type="submit" class="btn-ambar">Calificar</button></form>';
        }
        if (p.tiene_recibo) acciones += '<a class="btn btn-outline" href="/cliente/pedido/' + p.id + '/recibo">Ver recibo</a>';
        return '<div class="card"><div class="fila"><strong>Pedido #' + p.id + " — " + esc(p.nombre_restaurante) + "</strong>" + insignia(p) + "</div>" +
          '<p class="muted">Total: ' + dinero(p.monto_total) + " · " + esc(p.tipo_entrega) + '</p><div style="display:flex; gap:8px; flex-wrap:wrap;">' + acciones + "</div></div>";
      }).join("");
    }

    cont.addEventListener("click", async (ev) => {
      const b = ev.target.closest(".b-confirmar");
      if (!b) return;
      const r = await ejecutar(b, () => api("POST", "/pedidos/" + b.dataset.id + "/recepcion"));
      if (r) { await cargar(); aviso(r.message, "success"); }
    });
    cont.addEventListener("submit", async (ev) => {
      const f = ev.target.closest(".f-calificar");
      if (!f) return;
      ev.preventDefault();
      const r = await ejecutar($("button", f), () => api("POST", "/pedidos/" + f.dataset.id + "/calificacion",
        { puntuacion: Number(f.elements.puntuacion.value), comentario: f.elements.comentario.value }));
      if (r) { await cargar(); aviso(r.message, "success"); }
    });
    cargar();
  };

  // ---- cliente: pagar
  paginas.cliente_pagar = async function (app) {
    const id = app.dataset.pedidoId;
    const cont = $("#contenido");
    const r = await ejecutar(null, () => api("GET", "/pedidos/" + id));
    if (!r) { cont.innerHTML = '<a class="btn" href="/cliente/pedidos">Volver a mis pedidos</a>'; return; }
    const p = r.data;
    $("#titulo").textContent = "Pagar pedido #" + p.id;

    cont.innerHTML =
      '<div class="card">' + p.detalles.map((d) => '<div class="fila"><span>' + d.cantidad + " x " + esc(d.nombre) + "</span><span>" + dinero(d.subtotal) + "</span></div>").join("") +
      '<h3 style="text-align:right;">Total a pagar: ' + dinero(p.monto_total) + "</h3></div>" +
      '<details class="card" open><summary><strong>Pago simulado</strong></summary>' +
      '<form id="form-pago"><label>Medio de pago</label>' +
      '<select name="tipo_pago" id="tipo_pago"><option value="TARJETA_CREDITO">Tarjeta de crédito</option>' +
      '<option value="TARJETA_DEBITO">Tarjeta débito</option><option value="PSE">PSE</option><option value="TRANSFERENCIA">Transferencia bancaria</option></select>' +
      '<div id="campos_tarjeta"><label>Número de tarjeta</label><input type="text" name="numero_tarjeta" placeholder="4111111111111111" maxlength="19" autocomplete="off">' +
      '<label>Fecha de expiración (MM/AA)</label><input type="text" name="fecha_expiracion" placeholder="12/28" autocomplete="off">' +
      '<label>CVV</label><input type="text" name="cvv" placeholder="123" maxlength="4" autocomplete="off"></div>' +
      '<div id="campos_pse" style="display:none;"><label>Banco</label><input type="text" name="banco_pse" placeholder="Bancolombia"></div>' +
      '<div id="campos_transferencia" style="display:none;"><label>Banco de origen</label><input type="text" name="banco_transferencia" placeholder="Banco de Bogotá">' +
      '<label>Número de comprobante</label><input type="text" name="numero_referencia" placeholder="123456"></div>' +
      '<button type="submit">Pagar ' + dinero(p.monto_total) + "</button></form>" +
      '<p class="muted">Prueba: una tarjeta terminada en 0000 simula fondos insuficientes, y en 9999 simula timeout.</p></details>';

    const form = $("#form-pago");
    const mostrar = () => {
      const t = form.elements.tipo_pago.value;
      $("#campos_tarjeta").style.display = t.startsWith("TARJETA") ? "block" : "none";
      $("#campos_pse").style.display = t === "PSE" ? "block" : "none";
      $("#campos_transferencia").style.display = t === "TRANSFERENCIA" ? "block" : "none";
    };
    form.elements.tipo_pago.addEventListener("change", mostrar);
    mostrar();

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const t = form.elements.tipo_pago.value;
      // Solo se envían los campos del medio de pago elegido -> el Payload queda limpio y correcto.
      const cuerpo = { tipo_pago: t };
      if (t.startsWith("TARJETA")) {
        cuerpo.numero_tarjeta = form.elements.numero_tarjeta.value.trim();
        cuerpo.fecha_expiracion = form.elements.fecha_expiracion.value.trim();
        cuerpo.cvv = form.elements.cvv.value.trim();
      } else if (t === "PSE") {
        cuerpo.banco = form.elements.banco_pse.value.trim();
      } else {
        cuerpo.banco = form.elements.banco_transferencia.value.trim();
        cuerpo.numero_referencia = form.elements.numero_referencia.value.trim();
      }
      const res = await ejecutar($("button[type=submit]", form), () => api("POST", "/pedidos/" + id + "/pago", cuerpo));
      if (res) avisoDespues(res.message, "success", res.data.redirect);
    });
  };

  // ---- cliente: recibo
  paginas.cliente_recibo = async function (app) {
    const id = app.dataset.pedidoId;
    const cont = $("#contenido");
    const r = await ejecutar(null, () => api("GET", "/pedidos/" + id + "/recibo"));
    const volver = '<a class="btn" href="/cliente/pedidos">Volver a mis pedidos</a>';
    if (!r) { cont.innerHTML = volver; return; }
    cont.innerHTML = r.data.disponible
      ? '<pre class="recibo">' + esc(r.data.recibo) + "</pre>" + volver
      : '<p class="muted">Aún no hay recibo para este pedido (el pago no se ha aprobado todavía).</p>' + volver;
  };

  // ---- chef: pedidos
  paginas.chef_panel = async function () {
    const cont = $("#contenido");

    async function cargar() {
      const r = await ejecutar(null, () => api("GET", "/chef/pedidos"));
      if (!r) return;
      const rest = r.restaurante;
      if (!rest) { cont.innerHTML = '<p class="muted">No tienes un restaurante asociado.</p>'; return; }
      if (rest.estado !== "PUBLICADO") {
        cont.innerHTML = '<div class="card"><p>Tu restaurante aún no está publicado. Configura tu perfil, agrega tus platillos y publícalo para recibir pedidos.</p>' +
          '<a class="btn" href="/chef/menu">Configurar menú y publicar</a></div>';
        return;
      }
      if (!r.data.length) { cont.innerHTML = '<p class="muted">Todavía no tienes pedidos.</p>'; return; }
      cont.innerHTML = r.data.map((p) => {
        let acciones = "";
        p.acciones.forEach((a) => {
          if (a.accion === "rechazar") {
            acciones += '<form class="f-rechazar" data-url="' + esc(a.url) + '"><input type="text" name="motivo" placeholder="Motivo (opcional)" style="width:160px;"> <button class="btn-secondary" type="submit">Rechazar</button></form>';
          } else {
            const clase = a.accion === "aceptar" ? "btn-verde" : a.accion === "despachar" ? "btn-ambar" : "";
            acciones += '<button type="button" class="b-accion ' + clase + '" data-url="' + esc(a.url) + '">' + esc(a.etiqueta) + "</button>";
          }
        });
        if (p.estado === "PENDIENTE_CHEF" && p.aceptado_por_chef) acciones += '<span class="muted">Aceptado — esperando pago del cliente</span>';
        return '<div class="card"><div class="fila"><strong>Pedido #' + p.id + "</strong>" + insignia(p) + "</div>" +
          p.detalles.map((d) => '<div class="muted">' + d.cantidad + " x " + esc(d.nombre) + " — " + dinero(d.subtotal) + "</div>").join("") +
          '<p class="muted">Total: ' + dinero(p.monto_total) + " · " + (p.tipo_entrega === "DOMICILIO" ? "Domicilio" : "Recoger en el local") +
          (p.direccion_entrega ? " — " + esc(p.direccion_entrega) : "") + '</p><div style="display:flex; gap:8px; flex-wrap:wrap;">' + acciones + "</div></div>";
      }).join("");
    }

    const llamar = (url, cuerpo) => api("POST", url.replace("/api/v1", ""), cuerpo);
    cont.addEventListener("click", async (ev) => {
      const b = ev.target.closest(".b-accion");
      if (!b) return;
      const r = await ejecutar(b, () => llamar(b.dataset.url));
      if (r) { await cargar(); aviso(r.message, "success"); }
    });
    cont.addEventListener("submit", async (ev) => {
      const f = ev.target.closest(".f-rechazar");
      if (!f) return;
      ev.preventDefault();
      const r = await ejecutar($("button", f), () => llamar(f.dataset.url, { motivo: f.elements.motivo.value }));
      if (r) { await cargar(); aviso(r.message, "info"); }
    });
    cargar();
  };

  // ---- chef: restaurante y menú
  paginas.chef_menu = async function () {
    const cont = $("#contenido");
    let estado = null;

    const campoPerfil = (r) =>
      '<label>Nombre del restaurante</label><input type="text" name="nombre_restaurante" value="' + esc(r.nombre_restaurante) + '" required>' +
      '<label>Dirección</label><input type="text" name="direccion" value="' + esc(r.direccion) + '" required>' +
      '<label>Descripción</label><textarea name="descripcion" rows="2">' + esc(r.descripcion || "") + "</textarea>" +
      '<label>Hora de apertura</label><input type="time" name="hora_apertura" value="' + esc(r.hora_apertura || "08:00") + '" required>' +
      '<label>Hora de cierre</label><input type="time" name="hora_cierre" value="' + esc(r.hora_cierre || "20:00") + '" required>';

    const campoPlatillo = (boton) =>
      '<label>Nombre</label><input type="text" name="nombre" required>' +
      '<label>Descripción</label><input type="text" name="descripcion">' +
      '<label>Precio</label><input type="number" name="precio" min="1" step="1" required>' +
      '<label>Inventario (unidades disponibles)</label><input type="number" name="inventario" min="0" step="1" required>' +
      '<button type="submit" class="btn-verde">' + boton + "</button>";

    function dibujar() {
      const rest = estado.restaurante;
      if (!rest) { cont.innerHTML = '<p class="muted">No tienes un restaurante asociado.</p>'; return; }
      if (rest.estado !== "PUBLICADO") {
        const b = estado.borrador_platillos;
        cont.innerHTML =
          '<div class="card"><p class="muted">Completa tu perfil, agrega al menos un platillo y publica tu restaurante.</p>' +
          '<form id="f-publicar">' + campoPerfil(rest) + "<h3>Platillos agregados (" + b.length + ")</h3>" +
          (b.length ? "" : '<p class="muted">Agrega al menos un platillo abajo antes de publicar.</p>') +
          b.map((pl) => '<div class="fila"><span>' + esc(pl.nombre) + " — " + dinero(pl.precio) + " (stock " + pl.inventario + ")</span></div>").join("") +
          '<button type="submit"' + (b.length ? "" : " disabled") + ">Guardar y publicar restaurante</button></form></div>" +
          '<div class="card"><h3>Agregar platillo</h3><form id="f-borrador">' + campoPlatillo("+ Agregar a la lista") + "</form>" +
          (b.length ? "<h4>Quitar de la lista</h4>" + b.map((pl) => '<button type="button" class="btn-secondary b-quitar-borrador" data-indice="' + pl.indice + '">Quitar "' + esc(pl.nombre) + '"</button> ').join("") : "") + "</div>";
      } else {
        cont.innerHTML =
          '<div class="card"><h3>Perfil del restaurante</h3><form id="f-perfil">' + campoPerfil(rest) + '<button type="submit">Guardar cambios del perfil</button></form></div>' +
          '<div class="card"><h3>Menú publicado</h3>' +
          (estado.menu_publicado.length ? "" : '<p class="muted">Aún no tienes platillos activos.</p>') +
          estado.menu_publicado.map((p) => '<div class="fila"><span><strong>' + esc(p.nombre) + "</strong> — " + dinero(p.precio) + " · stock: " + p.inventario +
            (p.descripcion ? '<br><span class="muted">' + esc(p.descripcion) + "</span>" : "") + "</span>" +
            '<span style="display:flex; gap:6px;"><a class="btn btn-outline" href="/chef/producto/' + p.id + '/editar">Editar</a>' +
            '<button type="button" class="btn-secondary b-quitar-publicado" data-id="' + p.id + '" data-nombre="' + esc(p.nombre) + '">Quitar</button></span></div>').join("") + "</div>" +
          '<div class="card"><h3>Agregar un platillo nuevo</h3><form id="f-menu">' + campoPlatillo("+ Agregar al menú") + "</form></div>";
      }
    }

    async function cargar(mensaje, nivel) {
      const r = await ejecutar(null, () => api("GET", "/chef/restaurante"));
      if (!r) return;
      estado = r.data;
      dibujar();
      if (mensaje) aviso(mensaje, nivel || "success");
    }

    cont.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = ev.target, boton = $("button[type=submit]", f);
      if (f.id === "f-publicar") {
        const r = await ejecutar(boton, () => api("POST", "/chef/restaurante/publicacion", datosForm(f)));
        if (r) avisoDespues(r.message, "success", r.data.redirect);
      } else if (f.id === "f-borrador") {
        const r = await ejecutar(boton, () => api("POST", "/chef/borrador/platillos", datosForm(f)));
        if (r) await cargar(r.message);
      } else if (f.id === "f-perfil") {
        const r = await ejecutar(boton, () => api("PUT", "/chef/restaurante", datosForm(f)));
        if (r) await cargar(r.message);
      } else if (f.id === "f-menu") {
        const r = await ejecutar(boton, () => api("POST", "/chef/menu", datosForm(f)));
        if (r) await cargar(r.message);
      }
    });
    cont.addEventListener("click", async (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      if (b.classList.contains("b-quitar-borrador")) {
        const r = await ejecutar(b, () => api("DELETE", "/chef/borrador/platillos/" + b.dataset.indice));
        if (r) await cargar(r.message, "info");
      } else if (b.classList.contains("b-quitar-publicado")) {
        if (!confirm("¿Retirar '" + b.dataset.nombre + "' del menú?")) return;
        const r = await ejecutar(b, () => api("DELETE", "/restaurantes/" + estado.restaurante.id + "/menu/" + b.dataset.id));
        if (r) await cargar(r.message, "info");
      }
    });
    cargar();
  };

  // ---- chef: editar platillo
  paginas.chef_editar_producto = async function (app) {
    const id = app.dataset.productoId;
    const cont = $("#contenido");
    const r = await ejecutar(null, () => api("GET", "/chef/menu/" + id));
    if (!r) { cont.innerHTML = '<a href="/chef/menu">&larr; Volver a mi menú</a>'; return; }
    const p = r.data;
    cont.innerHTML = '<div class="card" style="max-width:480px;"><form id="f-editar">' +
      '<label>Nombre del platillo</label><input type="text" name="nombre" value="' + esc(p.nombre) + '" required>' +
      '<label>Descripción</label><textarea name="descripcion" rows="2">' + esc(p.descripcion || "") + "</textarea>" +
      '<label>Precio</label><input type="number" name="precio" value="' + esc(p.precio) + '" min="1" step="1" required>' +
      '<label>Stock disponible</label><input type="number" name="inventario" value="' + esc(p.inventario) + '" min="0" step="1" required>' +
      '<button type="submit">Guardar cambios</button></form></div>';
    $("#f-editar").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const res = await ejecutar($("button[type=submit]", ev.target), () => api("PUT", "/chef/menu/" + id, datosForm(ev.target)));
      if (res) avisoDespues(res.message, "success", res.data.redirect);
    });
  };

  // ------------------------------------------------------------------ arranque
  document.addEventListener("DOMContentLoaded", () => {
    mostrarAvisoGuardado();
    const salir = $("#btn-salir");
    if (salir) {
      salir.addEventListener("click", async (ev) => {
        ev.preventDefault();
        const r = await ejecutar(null, () => api("POST", "/auth/logout"));
        location.href = r ? r.data.redirect : "/login";
      });
    }
    const app = $("#app");
    if (app && paginas[app.dataset.page]) paginas[app.dataset.page](app);
  });
})();
