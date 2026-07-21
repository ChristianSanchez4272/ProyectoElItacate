"use strict";

const btnInfo = document.getElementById("btnInfo");
const btnRecetas = document.getElementById("btnRecetas");
const informacion = document.getElementById("informacion");
const politicas = document.getElementById("politicas");
const textoPoliticas = document.getElementById("textoPoliticas");
const aceptaPoliticas = document.getElementById("aceptaPoliticas");
const btnAceptar = document.getElementById("btnAceptar");
const chat = document.getElementById("chat");
const mensajes = document.getElementById("mensajes");
const formularioChat = document.getElementById("formularioChat");
const entradaChat = document.getElementById("entradaChat");
const btnEnviar = document.getElementById("btnEnviar");
const btnNuevaConsulta = document.getElementById("btnNuevaConsulta");

const estado = { fase: "ingredientes", ingredientes: "" };

btnInfo.addEventListener("click", () => informacion.classList.toggle("oculto"));
btnRecetas.addEventListener("click", mostrarPoliticas);
aceptaPoliticas.addEventListener("change", () => { btnAceptar.disabled = !aceptaPoliticas.checked; });
btnAceptar.addEventListener("click", iniciarChat);
btnNuevaConsulta.addEventListener("click", iniciarConsulta);
formularioChat.addEventListener("submit", enviarMensaje);

async function mostrarPoliticas() {
    btnRecetas.disabled = true;
    politicas.classList.remove("oculto");
    try {
        const respuesta = await fetch("/api/policies");
        const datos = await respuesta.json();
        if (!respuesta.ok) throw new Error(datos.error || "No fue posible cargar las políticas.");
        textoPoliticas.textContent = datos.policy;
    } catch (error) {
        textoPoliticas.textContent = error.message;
    } finally {
        btnRecetas.disabled = false;
    }
}

function iniciarChat() {
    politicas.classList.add("oculto");
    chat.classList.remove("oculto");
    iniciarConsulta();
}

function iniciarConsulta() {
    estado.fase = "ingredientes";
    estado.ingredientes = "";
    estado.personas = "";
    estado.opciones = [];
    mensajes.replaceChildren();
    agregarMensaje("agente", "¡Hola! Soy Chef IA. ¿Qué ingredientes tienes disponibles? Escríbelos separados por comas.");
    entradaChat.value = "";
    entradaChat.placeholder = "Ejemplo: pollo, jitomate, chiles";
    entradaChat.disabled = false;
    btnEnviar.disabled = false;
    entradaChat.focus();
}

async function enviarMensaje(evento) {
    evento.preventDefault();
    const mensaje = entradaChat.value.trim();
    if (!mensaje) return;

    agregarMensaje("usuario", mensaje);
    entradaChat.value = "";
    if (estado.fase === "ingredientes") {
        estado.ingredientes = mensaje;
        estado.fase = "personas";
        entradaChat.placeholder = "Ejemplo: 2";
        agregarMensaje("agente", "¿Para cuántas personas cocinarás?");
        return;
    }

    if (estado.fase === "personas") {
        await solicitarOpciones(mensaje);
        return;
    }

    if (estado.fase === "opciones") {
        const indice = Number(mensaje) - 1;
        if (!Number.isInteger(indice) || !estado.opciones[indice]) {
            agregarMensaje("agente", "Escribe el número de una de las opciones mostradas.");
            return;
        }
        await solicitarReceta(estado.personas, estado.opciones[indice].name);
    }
}

async function solicitarOpciones(personas) {
    bloquearFormulario(true);
    const estadoMensaje = agregarMensaje("estado", "Chef IA está buscando opciones…");
    try {
        const respuesta = await fetch("/api/options", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ingredients: estado.ingredientes, servings: personas })
        });
        const datos = await respuesta.json();
        if (!respuesta.ok) throw new Error(datos.error || "No fue posible buscar recetas.");
        estadoMensaje.remove();
        estado.personas = personas;
        estado.opciones = datos.options;
        const textoOpciones = datos.options.map((opcion, indice) => (
            `${indice + 1}. ${opcion.name} — ${opcion.preparation_time}, dificultad ${opcion.difficulty}`
        )).join("\n");
        agregarMensaje("agente", `Estas son las opciones basadas en ${estado.ingredientes.split(",")[0].trim()}:\n${textoOpciones}\n\nEscribe el número de la receta que prefieras.`);
        estado.fase = "opciones";
        entradaChat.placeholder = "Ejemplo: 1";
        bloquearFormulario(false);
    } catch (error) {
        estadoMensaje.remove();
        agregarMensaje("agente", error.message);
        estado.fase = "personas";
        entradaChat.placeholder = "Escribe nuevamente el número de personas";
        bloquearFormulario(false);
    }
}

async function solicitarReceta(personas, recetaElegida) {
    bloquearFormulario(true);
    const estadoMensaje = agregarMensaje("estado", "Chef IA está preparando tu receta…");
    try {
        const respuesta = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                ingredients: estado.ingredientes,
                servings: personas,
                recipe_name: recetaElegida
            })
        });
        const datos = await respuesta.json();
        if (!respuesta.ok) throw new Error(datos.error || "No fue posible generar la receta.");
        estadoMensaje.remove();
        agregarMensaje("agente", datos.reply);
        estado.fase = "finalizada";
        entradaChat.placeholder = "Usa “Nueva consulta” para cocinar otro platillo";
    } catch (error) {
        estadoMensaje.remove();
        agregarMensaje("agente", error.message);
        estado.fase = "opciones";
        entradaChat.placeholder = "Escribe el número de una opción";
        bloquearFormulario(false);
    }
}

function bloquearFormulario(bloqueado) {
    entradaChat.disabled = bloqueado;
    btnEnviar.disabled = bloqueado;
}

function agregarMensaje(tipo, texto) {
    const elemento = document.createElement("div");
    elemento.className = `mensaje ${tipo}`;
    elemento.textContent = texto;
    mensajes.append(elemento);
    mensajes.scrollTop = mensajes.scrollHeight;
    return elemento;
}
