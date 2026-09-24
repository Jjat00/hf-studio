# HF Studio · UI web

Interfaz Next.js 16 de HF Studio. La puesta en marcha, la configuración (`web/.env.local`) y la arquitectura están en
el [README principal](../README.md).

El proxy `/api/studio` pone la clave de la UI en cada petición sin autenticar a quien la visita, y con
`hf-studio see-all web-ui` esa clave ve y gestiona las generaciones de todos los clientes. Por eso `pnpm dev`
escucha solo en `127.0.0.1`: no lo expongas a otras máquinas (`--hostname 0.0.0.0`, túneles, despliegues) sin
poner autenticación delante.

```bash
pnpm install
pnpm dev     # http://localhost:3000, solo en esta máquina (necesita la API en :8787)
```
