# MiniTask Clon

Grabador y reproductor de ratón y teclado para Windows, para automatizar tareas
repetitivas. Código abierto, licencia MIT.

> Es un clon independiente, escrito desde cero. No es el programa original ni está
> afiliado a sus autores. Por eso el icono es un puntero con una copia detrás.

## Uso

- **F8**: empezar / parar grabación
- **F9**: reproducir / parar
- Repeticiones (0 = infinito) y velocidad ajustables
- Guardar y abrir grabaciones en `.json`

Desde el código: `pip install -r requirements.txt` y `python minitask.py`.

## Qué hace y qué no hace

MiniTask solo graba y reproduce eventos de ratón y teclado **en tu propio equipo**.
No tiene acceso a la red, no envía datos a ningún sitio y no se ejecuta en segundo
plano: solo escucha mientras la ventana está abierta.

Ten en cuenta que una grabación incluye todo lo que escribes (contraseñas incluidas).
No grabes ni guardes sesiones donde las teclees. Las grabaciones cargadas de un
archivo se validan y piden confirmación antes de reproducirse.

## Política de firma de código

Los ejecutables publicados en las Releases se firman con un certificado
proporcionado por [SignPath Foundation](https://signpath.org) mediante
[SignPath.io](https://signpath.io). Solo se firman binarios generados por
GitHub Actions a partir del código de este repositorio.

- Autores y revisores: los mantenedores del repositorio.
- Aprobadores de la firma: los propietarios del repositorio.

## Política de privacidad

Este programa no transfiere ninguna información a otros sistemas, salvo que el
usuario lo haga expresamente (por ejemplo, compartiendo un archivo de grabación).
