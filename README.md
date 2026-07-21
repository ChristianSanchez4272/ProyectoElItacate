# El Itacate

Agente de recetas mexicanas con LangChain y Cohere. Solo recomienda recetas existentes
en la biblioteca del proyecto y usa `Ingredientes.docx` para normalizar ingredientes y
completar faltantes autorizados.

## Estructura de rutas

La base documental permanece en la raíz del repositorio y el código está separado en
`Agente Itacate`. En ejecución local, las rutas se resuelven automáticamente a rutas
absolutas. En Render, el contenedor usa estas rutas absolutas:

```text
/app/                         # Base documental, HTML e imagen
/app/src/chef_ia/             # Código Python
/app/html/                    # Vista web
```

No se usan rutas de Windows en producción ni se requiere `--data-dir ..` al desplegar.

## Ejecutar localmente

Desde PowerShell:

```powershell
cd "C:\Users\Angela\Documents\Agente IA\Agente Itacate"
$env:PYTHONPATH = "src"
& ".\.venv\Scripts\python.exe" -B -m chef_ia.web_server --data-dir ..
```

Abre `http://localhost:8080` y mantén la consola abierta mientras usas la aplicación.

## Configurar Cohere

Para uso local, crea `.env` a partir de `.env.example` y agrega:

```text
COHERE_API_KEY=tu_clave_privada
```

No subas el archivo `.env` al repositorio.

## Desplegar en Render

El repositorio incluye [render.yaml](../render.yaml) y [Dockerfile](../Dockerfile). Render
construye la imagen automáticamente y ejecuta el servidor en `0.0.0.0` usando el puerto
que proporciona en la variable `PORT`. El health check configurado es `/health`.

1. Sube el repositorio completo a GitHub, incluyendo la carpeta `Agente Itacate`, `html`,
   los archivos `.docx`, `Dockerfile` y `render.yaml`.
2. En Render, selecciona **New** → **Blueprint** y conecta el repositorio.
3. Render detectará el servicio `el-itacate` definido en `render.yaml`.
4. En la configuración del servicio, agrega la variable secreta `COHERE_API_KEY` con la
   clave de Cohere. No copies `.env` a Render.
5. Crea el servicio y espera a que el estado sea **Live**. Abre la URL `https://...onrender.com`
   que Render muestra en el panel.

Render debe conservar `PORT` tal como lo asigna la plataforma. No configures `8080` ni
`0.0.0.0` como URL del navegador: esos valores son solo para el proceso del servidor.

## Pruebas

```powershell
cd "C:\Users\Angela\Documents\Agente IA\Agente Itacate"
$env:PYTHONPATH = "src"
& ".\.venv\Scripts\python.exe" -B -m unittest discover -s tests -v
```

## Normalización de ingredientes

`Ingredientes.docx` es la fuente de verdad. El catálogo normaliza mayúsculas, acentos,
singular/plural, variantes de chile y queso, además de las categorías comunes del documento.
Por ejemplo, `carne` puede representar `carne de res` o `carne de cerdo`, y `verduras`
puede representar ingredientes como jitomate o papa. No se agregan ingredientes externos
al documento.
