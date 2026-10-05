/** Casos de uso: qué se puede hacer con HF Studio, desde la UI y desde el MCP, con mini tutorial y prompts. */
import { l, type L } from "./i18n";
import type { AudioService } from "./studio";

export type Channel = "ui" | "mcp";

export type Step = { title: L; body?: L; tool?: string };

export type Category = "Cinematic" | "Product" | "Animate" | "Motion" | "Edit" | "Audio" | "Social" | "Agents";

export type UseCase = {
  slug: string;
  title: L;
  tagline: L;
  category: Category;
  output: "video" | "image" | "audio";
  channels: Channel[];
  art: string;
  model: string;
  /** Entrada de ejemplo para cotizar en vivo (el costo se muestra siempre antes de generar). Sin ella, se cotiza con tus medios. */
  sample?: Record<string, unknown>;
  /** Casos de ElevenLabs: se cotizan con su servicio de audio, no con el catálogo de Higgsfield. */
  audio?: { service: AudioService; body: Record<string, unknown> };
  /** Qué cubre el costo de ejemplo cuando el caso tiene varias etapas. */
  costNote?: L;
  /** Estudio de la UI (sin el prompt): `?prompt=` se añade al usar un ejemplo. */
  uiHref?: string;
  preset?: string;
  ui?: Step[];
  /** Lo que le pides a tu agente, en lenguaje natural. */
  ask: L;
  mcp: Step[];
  /** Los prompts van en inglés en ambos idiomas: es lo que entra al modelo. */
  prompts: { label: L; text: string }[];
  tips: L[];
};

const studioHref = (path: "video" | "image", tab: string, mode: string, model: string) =>
  `/${path}?${new URLSearchParams({ tab, mode, model })}`;

export const USE_CASES: UseCase[] = [
  {
    slug: "establishing-shot",
    title: l("Plano de apertura cinematográfico", "Cinematic establishing shot"),
    tagline: l("Abre tu película, reel o landing con un plano amplio de cualquier lugar.", "Open your film, reel or landing page with a sweeping shot of any place."),
    category: "Cinematic",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/establishing.webp",
    model: "bytedance/seedance-2.0/text-to-video",
    sample: { prompt: "cost preview", duration: 5, resolution: "480p", aspect_ratio: "21:9", generate_audio: true },
    uiHref: studioHref("video", "create", "text", "bytedance/seedance-2.0/text-to-video"),
    preset: "cinematic-establishing",
    ui: [
      { title: l("Abre Video › Texto", "Open Video › Text"), body: l("Seedance 2.0 viene seleccionado. Si quieres otro modelo, elígelo en el selector de modelo.", "Seedance 2.0 is selected by default. Pick another model from the model chip if you want.") },
      { title: l("Escribe el plano", "Write the shot"), body: l("Lugar + hora del día + movimiento de cámara + lente. Basta una frase; pega uno de los prompts de abajo.", "Place + time of day + camera move + lens. One sentence is enough; paste one of the prompts below.") },
      { title: l("Elige formato y duración", "Set format and length"), body: l("21:9 o 16:9 para cine, 9:16 para reels. Empieza con 5 s a 480p mientras iteras.", "21:9 or 16:9 for film, 9:16 for reels. Start with 5 s at 480p while you iterate.") },
      { title: l("Mira el costo y pulsa Generar", "Check the cost, then Generate"), body: l("El precio se actualiza al cambiar los ajustes. No se gasta nada hasta que pulsas Generar.", "The price updates as you change settings. Nothing is spent until you press Generate.") },
      { title: l("Itera", "Iterate"), body: l("Desde la Biblioteca, reutiliza la generación, ajusta la línea de cámara y sube a 720p o 1080p.", "From the Library, Reuse the generation, tweak the camera line and upscale to 720p or 1080p.") },
    ],
    ask: l(
      "Hazme un plano de apertura de 5 segundos en 21:9 de un pueblo pesquero con niebla al amanecer. Muéstrame primero el costo.",
      "Make me a 5 second 21:9 establishing shot of a foggy fishing village at dawn. Show me the cost first.",
    ),
    mcp: [
      { title: l("Busca la receta", "Find the recipe"), body: l("El agente lista las recetas listas y elige la de plano de apertura.", "The agent lists ready-made recipes and picks the establishing-shot one."), tool: "list_presets" },
      { title: l("Cotiza", "Quote it"), body: l("Ejecuta el preset con dry_run y te muestra los créditos y los USD.", "Runs the preset with dry_run and shows you the credits and USD."), tool: "run_preset" },
      { title: l("Genera con tu OK", "Generate on your OK"), body: l("La misma llamada con dry_run: false, el quote_id de la cotización (prueba de que viste el precio) y una clave de idempotencia, para que nunca cobre dos veces.", "Same call with dry_run: false, the quote_id from the quote (proof you saw the price) and an idempotency key, so it never charges twice."), tool: "run_preset" },
      { title: l("Espera y descarga", "Wait and download"), body: l("Espera con long-poll hasta que termina y guarda el MP4 en tu proyecto.", "Long-polls until it finishes and saves the MP4 to your project."), tool: "get_generation → download_outputs" },
    ],
    prompts: [
      { label: l("Pueblo pesquero", "Fishing village"), text: "Cinematic establishing shot of a foggy fishing village at dawn, slow aerial push-in, anamorphic lens, natural film grain, warm window lights through the mist" },
      { label: l("Carretera en el desierto", "Desert highway"), text: "Wide establishing shot of an empty desert highway at golden hour, lateral tracking shot, heat haze, long shadows, 35mm film look" },
      { label: l("Ciudad de neón", "Neon city"), text: "Crane up reveal over a rainy neon city at night, reflections on wet streets, volumetric haze, cinematic blue and magenta palette" },
    ],
    tips: [
      l("Nombra el movimiento de cámara explícitamente: push-in, crane up, lateral tracking.", "Name the camera move explicitly: push-in, crane up, lateral tracking."),
      l("En Seedance el audio viene activado: apágalo si solo necesitas la imagen.", "Audio is on by default in Seedance: turn it off if you only need the picture."),
    ],
  },
  {
    slug: "product-launch",
    title: l("Pack de lanzamiento de producto", "Product launch pack"),
    tagline: l("Una foto hero de estudio de tu producto y luego el mismo plano como video giratorio 360°.", "A studio hero shot of your product, then the same shot as a 360° turntable video."),
    category: "Product",
    output: "image",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/product-launch.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "4:3", resolution: "1080p" },
    costNote: l("Solo la imagen hero. El video 360° se cotiza aparte, antes de generarlo.", "Hero image only. The 360° video is quoted separately, before you generate it."),
    uiHref: studioHref("image", "create", "text", "higgsfield-ai/soul/v2/standard"),
    preset: "hero-shot",
    ui: [
      { title: l("Escribe la imagen hero", "Write the hero image"), body: l("Imagen › Texto a imagen con Soul 2.0. Describe el producto, la superficie y la luz.", "Image › Text to image with Soul 2.0. Describe the product, the surface and the light.") },
      { title: l("Mira el costo y genera", "Check the cost, then generate"), body: l("Las imágenes cuestan céntimos. Genera 2 o 3 variantes y quédate con la de reflejos más limpios.", "Images cost cents. Generate 2–3 variants and keep the one with the cleanest reflections.") },
      { title: l("Prepara el video", "Set up the video"), body: l("Abre el preset Órbita 360 de producto y suelta la imagen. Se abre a 720p: cambia a 480p para una primera prueba más barata.", "Open the preset Product 360 orbit and drop the image in. It opens at 720p: switch to 480p for a cheaper first test.") },
      { title: l("Mira el costo del video y genera", "Check the video cost, then generate"), body: l("El video es la parte cara. Su precio se muestra antes de pulsar Generar.", "The video is the expensive part. Its price is shown before you press Generate.") },
      { title: l("Exporta", "Export"), body: l("Descarga los dos desde la Biblioteca para la landing y el anuncio.", "Download both from the Library for the landing page and the ad.") },
    ],
    ask: l(
      "Crea una foto hero de unos auriculares inalámbricos negro mate sobre cemento pulido y luego anímala como video en órbita 360. Cotiza los dos pasos antes de generar.",
      "Create a hero shot of matte black wireless headphones on polished concrete, then animate it as a 360 orbit video. Quote both steps before generating.",
    ),
    mcp: [
      { title: l("Cotiza la imagen", "Quote the image"), body: l("Ejecuta el preset hero-shot con dry_run.", "Runs the hero-shot preset with dry_run."), tool: "run_preset" },
      { title: l("Genera y espera", "Generate and wait"), body: l("Genera la imagen y espera a tener la URL.", "Generates the image and waits for the URL."), tool: "run_preset → get_generation" },
      { title: l("Cotiza el video", "Quote the video"), body: l("Usa la URL resultante como foto para product-orbit y te muestra el precio.", "Uses the output URL as photo for product-orbit and shows you the price."), tool: "run_preset (product-orbit, dry_run)" },
      { title: l("Genera con tu OK", "Generate it on your OK"), tool: "run_preset → get_generation" },
      { title: l("Guarda los archivos", "Save the files"), body: l("Descarga el PNG y el MP4 en la carpeta public de tu repo.", "Downloads the PNG and the MP4 into your repo's public folder."), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("Auriculares", "Headphones"), text: "Premium studio hero shot of matte black wireless headphones on polished concrete, soft key light with a crisp rim light, shallow depth of field, clean negative space, commercial product photography, 85mm" },
      { label: l("Perfume", "Perfume"), text: "Luxury perfume bottle on white marble, morning light through a window, soft caustics, minimal composition, editorial beauty photography" },
      { label: l("Zapatilla", "Sneaker"), text: "Single white sneaker floating above reflective black glass, dramatic top light, dust particles, high-end sportswear campaign" },
    ],
    tips: [
      l("Deja espacio vacío si encima irá un titular.", "Leave negative space if a headline will go on top."),
      l("En el video, que el prompt de movimiento hable de la cámara, no del producto.", "For the video keep the motion prompt about the camera, not the product."),
    ],
  },
  {
    slug: "portrait-alive",
    title: l("Dale vida a una foto", "Bring a photo to life"),
    tagline: l("Movimiento sutil y natural para un retrato o una foto fija: respiración, pelo, luz.", "Subtle, natural motion for a portrait or a still: breathing, hair, light."),
    category: "Animate",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/portrait-alive.webp",
    model: "bytedance/seedance-2.0/image-to-video",
    sample: { prompt: "cost preview", image_url: "https://example.com/a.png", duration: 5, resolution: "480p", generate_audio: false },
    uiHref: studioHref("video", "create", "frames", "bytedance/seedance-2.0/image-to-video"),
    preset: "photo-to-life",
    ui: [
      { title: l("Abre Video › Inicio y final", "Open Video › Start & End"), body: l("Sube tu foto como fotograma inicial. Deja vacío el final.", "Upload your photo as the start frame. Leave the end frame empty.") },
      { title: l("Describe solo el movimiento", "Describe only the motion"), body: l("Qué se mueve y qué poco: pelo, ojos, tela, luz. La cámara casi quieta.", "What moves and how little: hair, eyes, fabric, light. Keep the camera almost still.") },
      { title: l("480p, 5 s, sin audio", "480p, 5 s, audio off"), body: l("La combinación más barata para probar si el movimiento se ve bien.", "The cheapest combination to test whether the motion feels right.") },
      { title: l("Genera", "Generate"), body: l("Mira el costo y genera. Sube la calidad cuando se vea natural.", "Check the cost chip, then generate. Scale up once it looks natural.") },
    ],
    ask: l(
      "Anima ~/Pictures/abuela.jpg con un movimiento sutil y natural, el pelo moviéndose con el viento. 480p, sin audio. Primero el costo.",
      "Animate ~/Pictures/grandma.jpg with subtle natural motion, hair moving in the wind. 480p, no audio. Cost first.",
    ),
    mcp: [
      { title: l("Sube la foto", "Upload the photo"), body: l("Envía el archivo local y obtiene una URL pública.", "Sends the local file and gets a public URL."), tool: "upload_media" },
      { title: l("Cotiza", "Quote"), body: l("Ejecuta photo-to-life con la URL como foto.", "Runs photo-to-life with the URL as photo."), tool: "run_preset (dry_run)" },
      { title: l("Genera y espera", "Generate and wait"), body: l("Con tu OK genera y espera.", "On your OK it generates and waits."), tool: "run_preset → get_generation" },
      { title: l("Descarga", "Download"), body: l("Guarda el MP4 junto a la foto original.", "Saves the MP4 next to the original photo."), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("Retrato", "Portrait"), text: "Subtle natural motion, hair moving in a light breeze, slow blink, gentle smile forming, camera almost still, realistic" },
      { label: l("Paisaje", "Landscape"), text: "Clouds drifting slowly, water shimmering, grass swaying, static camera, peaceful and realistic" },
      { label: l("Foto antigua", "Old photo"), text: "Vintage photograph coming to life, the person turns slightly towards the camera and smiles, film grain preserved, very subtle motion" },
    ],
    tips: [
      l("Menos es más: los movimientos grandes deforman las caras.", "Less is more: big motions distort faces."),
      l("Funcionan mejor las fotos con la cara visible y buena luz.", "Photos with a visible face and good light work best."),
    ],
  },
  {
    slug: "morph",
    title: l("Transición entre dos fotogramas", "Morph between two frames"),
    tagline: l("Una transición continua de una imagen a otra: estaciones, ropa, antes y después.", "A seamless transition from one image to another: seasons, outfits, before and after."),
    category: "Animate",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/morph.webp",
    model: "bytedance/seedance-2.0/image-to-video",
    sample: { prompt: "cost preview", image_url: "https://example.com/a.png", end_image_url: "https://example.com/b.png", duration: 5, resolution: "480p" },
    uiHref: studioHref("video", "create", "frames", "bytedance/seedance-2.0/image-to-video"),
    preset: "morph",
    ui: [
      { title: l("Prepara dos imágenes", "Prepare two images"), body: l("Mismo encuadre y mismo formato. Genéralas en Imagen si no las tienes.", "Same framing and aspect ratio. Generate them in Image if you don't have them.") },
      { title: l("Abre Video › Inicio y final", "Open Video › Start & End"), body: l("Fotograma inicial = donde empieza, fotograma final = donde termina.", "Start frame = where it begins, End frame = where it lands.") },
      { title: l("Nombra la transición", "Name the transition"), body: l("Fusión suave, la cámara atraviesa, destello de luz o transformación líquida.", "Smooth morph, camera push through, light burst or liquid transformation.") },
      { title: l("Genera a 480p", "Generate at 480p"), body: l("Mira primero el costo; si el recorrido se ve bien, repítelo a 720p.", "Check the cost first; if the path looks right, redo at 720p.") },
    ],
    ask: l(
      "Haz un video de transición de invierno.png a primavera.png con una transición de luz líquida. Muéstrame el precio antes de generar.",
      "Make a morph video from winter.png to spring.png with a liquid light transition. Show me the price before generating.",
    ),
    mcp: [
      { title: l("Sube los dos fotogramas", "Upload both frames"), body: l("Una llamada por archivo.", "One call per file."), tool: "upload_media ×2" },
      { title: l("Cotiza la transición", "Quote the morph"), body: l("Rellena inicio, final y estilo.", "Fills start, end and style."), tool: "run_preset (morph, dry_run)" },
      { title: l("Genera y recoge", "Generate and fetch"), body: l("Genera con tu OK, espera y descarga.", "Generates on your OK, waits and downloads."), tool: "run_preset → get_generation → download_outputs" },
    ],
    prompts: [
      { label: l("Estaciones", "Seasons"), text: "Liquid transformation from the first frame to the last frame, snow melting into spring flowers, continuous shot" },
      { label: l("Antes y después", "Before/after"), text: "Smooth morph from the empty room to the furnished room, camera slowly pushing in, continuous shot" },
      { label: l("Cambio de ropa", "Outfit change"), text: "Light burst transition, the outfit changes from the first frame to the last frame while the pose stays, continuous shot" },
    ],
    tips: [
      l("Cuanto más parecidos los dos encuadres, más limpia la transición.", "The closer the two framings, the cleaner the morph."),
      l("Menciona 'continuous shot' para evitar cortes.", "Mention 'continuous shot' to avoid cuts."),
    ],
  },
  {
    slug: "character-scenes",
    title: l("El mismo personaje, escenas nuevas", "Same character, new scenes"),
    tagline: l("Mantén un personaje coherente entre planos usando imágenes de referencia.", "Keep one character consistent across shots using reference images."),
    category: "Cinematic",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/character-scenes.webp",
    model: "bytedance/seedance-2.0/reference-to-video",
    sample: { prompt: "cost preview", image_urls: ["https://example.com/a.png"], duration: 5, resolution: "480p", aspect_ratio: "16:9" },
    uiHref: studioHref("video", "create", "references", "bytedance/seedance-2.0/reference-to-video"),
    preset: "character-in-scene",
    ui: [
      { title: l("Abre Video › Referencias", "Open Video › References"), body: l("Añade imágenes de tu personaje en Añadir elementos (hasta 9; suelen bastar 3 o 4 ángulos como frente, perfil y cuerpo entero).", "Add images of your character under Add elements (up to 9; 3–4 angles such as front, side and full body are usually enough).") },
      { title: l("Describe la escena nueva", "Describe the new scene"), body: l("Dónde está, qué hace y cómo se mueve la cámara. No vuelvas a describir su cara.", "Where they are, what they do and how the camera moves. Don't re-describe their face.") },
      { title: l("Genera una escena", "Generate one scene"), body: l("Primero a 480p. Mira el costo.", "480p first. Check the cost chip.") },
      { title: l("Repite para el siguiente plano", "Repeat for the next shot"), body: l("Reutiliza desde la Biblioteca y cambia solo la línea de la escena.", "Reuse from the Library and only change the scene line.") },
    ],
    ask: l(
      "Con las imágenes del personaje en ./refs, haz tres planos de 5 s: mercado de neón de noche, carretera en el desierto y bosque nevado. Cotiza primero todo el lote.",
      "Using the character images in ./refs, make three 5 s shots: neon market at night, desert road, snowy forest. Quote the whole batch first.",
    ),
    mcp: [
      { title: l("Sube las referencias", "Upload the references"), body: l("Una URL por imagen.", "One URL per image."), tool: "upload_media" },
      { title: l("Cotiza el lote", "Quote the batch"), body: l("Tres ítems con las mismas referencias y escenas distintas; devuelve el costo por ítem y el total.", "Three items with the same references and different scenes; returns cost per item and total."), tool: "generate_batch (dry_run)" },
      { title: l("Genera con tu OK", "Generate on your OK"), body: l("El mismo lote con dry_run: false.", "Same batch with dry_run: false."), tool: "generate_batch" },
      { title: l("Espera a todos", "Wait for all"), body: l("Una sola llamada espera los tres y los descarga.", "One call waits for the three and downloads them."), tool: "wait_generations → download_outputs" },
    ],
    prompts: [
      { label: l("Mercado nocturno", "Night market"), text: "The character walks through a neon night market, handheld camera following from behind, then turns to look at the lens" },
      { label: l("Carretera en el desierto", "Desert road"), text: "The character stands by an empty desert road at sunset, wind moving the raincoat, slow push-in" },
      { label: l("Bosque nevado", "Snow forest"), text: "The character walks between snowy pine trees, breath visible, lateral tracking shot, soft blue light" },
    ],
    tips: [
      l("Varios ángulos del mismo personaje valen más que una foto perfecta.", "Several angles of the same character beat one perfect photo."),
      l("Agrupa los planos en un lote para revisar el costo de toda la secuencia de una vez.", "Batch the shots so the whole sequence shares one cost check."),
    ],
  },
  {
    slug: "dance-transfer",
    title: l("Transferir baile y movimiento", "Dance and motion transfer"),
    tagline: l("Tu personaje hace los movimientos de cualquier video de referencia.", "Your character performs the moves of any reference video."),
    category: "Motion",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/dance-transfer.webp",
    model: "kling-video/v3/motion-control/std",
    sample: { image_url: "https://example.com/a.png", video_url: "https://example.com/a.mp4" },
    uiHref: studioHref("video", "motion", "motion", "kling-video/v3/motion-control/std"),
    preset: "dance-transfer",
    ui: [
      { title: l("Abre Control de movimiento", "Open Motion Control"), body: l("Añade el movimiento a copiar: un clip de 3 a 30 s con el cuerpo entero visible.", "Add the motion to copy: a clip of 3–30 s with the full body visible.") },
      { title: l("Añade tu personaje", "Add your character"), body: l("Una imagen con la cara y el cuerpo visibles, mejor en una pose parecida.", "An image with a visible face and body, ideally in a similar pose.") },
      { title: l("Prompt opcional", "Optional prompt"), body: l("Describe el lugar o la ropa; déjalo vacío para conservar la imagen del personaje.", "Describe the setting or outfit; leave it empty to keep the character's image.") },
      { title: l("El precio aparece al subir", "Price appears after upload"), body: l("Kling cobra por la duración del video, así que el costo se muestra cuando el clip está subido. Confirma y pulsa Generar.", "Kling prices by the video length, so the cost is shown once the clip is in. Confirm, then Generate.") },
    ],
    ask: l(
      "Haz que mi mascota de ./mascota.png haga el baile de ./baile.mp4. Conserva el sonido original. Dime primero el costo.",
      "Make my mascot in ./mascot.png do the dance in ./dance.mp4. Keep the original sound. Tell me the cost first.",
    ),
    mcp: [
      { title: l("Sube los dos archivos", "Upload both files"), body: l("Imagen y video.", "Image and video."), tool: "upload_media ×2" },
      { title: l("Cotiza con la duración del video", "Quote with the video length"), body: l("Ejecuta el preset dance-transfer como dry run con input_video_seconds, así el precio es exacto.", "Runs the dance-transfer preset as a dry run with input_video_seconds, so the price is exact."), tool: "run_preset (dry_run, input_video_seconds)" },
      { title: l("Genera con tu OK", "Generate on your OK"), body: l("La misma llamada con dry_run: false y el quote_id que devolvió.", "Same call with dry_run: false and the quote_id it returned."), tool: "run_preset (quote_id)" },
      { title: l("Espera y descarga", "Wait and download"), tool: "get_generation → download_outputs" },
    ],
    prompts: [
      { label: l("Escenario", "Stage"), text: "On a dark stage with spotlights, smoke on the floor, concert lighting" },
      { label: l("Calle", "Street"), text: "In a sunny street with graffiti walls, keep the outfit from the image" },
      { label: l("Sin prompt", "No prompt"), text: "" },
    ],
    tips: [
      l("Los clips de referencia más cortos cuestan menos: recorta los mejores 5–8 s.", "Shorter reference clips cost less: trim to the best 5–8 s."),
      l("Haz coincidir el formato de la imagen y el del video.", "Match the aspect ratio of the image and the video."),
    ],
  },
  {
    slug: "ad-multiplier",
    title: l("Multiplicador de anuncios", "Ad multiplier"),
    tagline: l("Cambia el producto de un anuncio existente y conserva todo lo demás: un anuncio, muchas variantes.", "Swap the product in an existing ad and keep everything else: one ad, many variants."),
    category: "Product",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/ad-multiplier.webp",
    model: "higgsfiled/genjutsu/object-swap/v1.0",
    sample: { video_url: "https://example.com/a.mp4", image_urls: ["https://example.com/a.png"], prompt: "cost preview", resolution: "720p" },
    uiHref: studioHref("video", "genjutsu", "swap", "higgsfiled/genjutsu/object-swap/v1.0"),
    preset: "ad-multiplier",
    ui: [
      { title: l("Abre Genjutsu › Cambiar objetos", "Open Genjutsu › Objects swap"), body: l("Sube el anuncio original (4–30 s, al menos 409.600 píxeles por fotograma, p. ej. 640×640).", "Upload the original ad (4–30 s, at least 409,600 pixels per frame, e.g. 640×640).") },
      { title: l("Añade el producto nuevo", "Add the new product"), body: l("Fotos limpias del producto, mejor sobre fondo liso.", "Clean product photos, ideally on a plain background.") },
      { title: l("Di qué reemplazar", "Say what to replace"), body: l("Señala el objeto: 'reemplaza la botella de su mano'.", "Point at the object: 'replace the bottle in her hand'.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Repite con cada producto para tener las variantes.", "Repeat with each product to get the variants.") },
    ],
    ask: l(
      "Toma ./anuncio.mp4 y haz tres versiones cambiando la botella por cada foto de ./botellas. Cotiza el lote y espera mi OK.",
      "Take ./ad.mp4 and make three versions swapping the bottle for each photo in ./bottles. Quote the batch, wait for my OK.",
    ),
    mcp: [
      { title: l("Sube el anuncio y los productos", "Upload the ad and products"), tool: "upload_media" },
      { title: l("Cotiza todas las variantes", "Quote all variants"), body: l("Un ítem por producto; pasa la duración del anuncio para que el total sea completo.", "One item per product; passes the ad's length so the total is complete."), tool: "generate_batch (dry_run, input_video_seconds)" },
      { title: l("Genera y espera", "Generate and wait"), tool: "generate_batch → wait_generations" },
      { title: l("Guárdalo como preset", "Save as a preset"), body: l("Conserva la configuración ganadora para la próxima campaña.", "Keep the winning setup for next campaign."), tool: "save_preset" },
    ],
    prompts: [
      { label: l("Botella", "Bottle"), text: "Replace the bottle in her hand with the product from the image, keep lighting and motion" },
      { label: l("Zapatillas", "Sneakers"), text: "Replace the sneakers on his feet with the new model, same colors of the scene" },
      { label: l("Lata", "Can"), text: "Swap the soda can on the table for the new can, keep reflections and condensation" },
    ],
    tips: [
      l("Sé concreto con el objeto: el modelo conserva todo lo demás.", "Be specific about which object: the model keeps everything else."),
      l("Genjutsu conserva el movimiento y el ritmo originales.", "Genjutsu keeps the original motion and timing."),
    ],
  },
  {
    slug: "restyle",
    title: l("Cambia el estilo de un clip", "Restyle a clip"),
    tagline: l("Reescribe cualquier video con un prompt: anime, plastilina, look de película, del día a la noche.", "Rewrite any video with a prompt: anime, claymation, film look, day to night."),
    category: "Edit",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/restyle.webp",
    model: "bytedance/seedance-2.5/video-edit",
    sample: { video_url: "https://example.com/a.mp4", prompt: "cost preview" },
    uiHref: studioHref("video", "edit", "edit", "bytedance/seedance-2.5/video-edit"),
    ui: [
      { title: l("Abre Editar video › Editar", "Open Edit Video › Edit"), body: l("Sube el clip o reutiliza una generación anterior desde la Biblioteca.", "Upload the clip, or reuse a previous generation from the Library.") },
      { title: l("Describe el nuevo look", "Describe the new look"), body: l("Estilo + lo que debe quedarse: 'como anime pintado a mano, conserva la cámara y el ritmo'.", "Style + what must stay: 'as a hand painted anime, keep the camera and timing'.") },
      { title: l("El costo es por segundo", "Cost is per second"), body: l("El precio aparece cuando el clip está cargado. Recorta antes los clips largos.", "The price appears once the clip is loaded. Trim long clips first.") },
      { title: l("Genera", "Generate"), body: l("Compáralo con el original en la Biblioteca.", "Compare with the original in the Library.") },
    ],
    ask: l(
      "Cambia el estilo de ./calle.mp4 a una escena de anime pintado a mano y conserva el movimiento de cámara. Cotiza primero con la duración real.",
      "Restyle ./street.mp4 as a hand painted anime scene, keep the camera move. Quote with the real length first.",
    ),
    mcp: [
      { title: l("Sube el clip", "Upload the clip"), tool: "upload_media" },
      { title: l("Cotiza con la duración", "Quote with the length"), tool: "estimate_cost (input_video_seconds)" },
      { title: l("Genera y espera", "Generate and wait"), tool: "generate → get_generation" },
      { title: l("Descarga", "Download"), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("Anime", "Anime"), text: "Restyle the whole video as a hand painted anime illustration, keep the camera motion and timing" },
      { label: l("Del día a la noche", "Day to night"), text: "Turn the scene into a rainy night with neon reflections, keep people and camera unchanged" },
      { label: l("Plastilina", "Claymation"), text: "Transform everything into a stop motion claymation look, visible fingerprints on the clay" },
    ],
    tips: [
      l("Di explícitamente lo que no debe cambiar.", "Say explicitly what must not change."),
      l("Los clips cortos (5–8 s) dan los resultados más coherentes.", "Short clips (5–8 s) give the most consistent results."),
    ],
  },
  {
    slug: "extend",
    title: l("Extiende un plano", "Extend a shot"),
    tagline: l("¿El plano terminó demasiado pronto? Continúalo desde su último fotograma.", "The shot ended too soon? Continue it from its last frame."),
    category: "Edit",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/extend.webp",
    model: "bytedance/seedance-2.5/video-extend",
    sample: { video_url: "https://example.com/a.mp4", prompt: "cost preview" },
    uiHref: studioHref("video", "edit", "extend", "bytedance/seedance-2.5/video-extend"),
    ui: [
      { title: l("Abre Editar video › Extender", "Open Edit Video › Extend"), body: l("Sube el clip que quieres continuar.", "Upload the clip to continue.") },
      { title: l("Di qué pasa después", "Say what happens next"), body: l("Continúa la acción y la cámara: 'el coche sigue avanzando y la cámara sube'.", "Continue the action and the camera: 'the car keeps driving and the camera rises'.") },
      { title: l("Mira el costo", "Check the cost"), body: l("Y pulsa Generar.", "Then Generate.") },
    ],
    ask: l(
      "Extiende la última generación 5 segundos más: el coche sigue por el acantilado y la cámara sube hasta revelar el mar.",
      "Extend the last generation 5 more seconds: the car keeps driving along the cliff and the camera rises to reveal the sea.",
    ),
    mcp: [
      { title: l("Busca el clip", "Find the clip"), body: l("Toma el último video terminado de tu historial.", "Takes the last completed video from your history."), tool: "list_generations" },
      { title: l("Cotiza la extensión", "Quote the extension"), tool: "estimate_cost" },
      { title: l("Genera y espera", "Generate and wait"), tool: "generate → get_generation" },
    ],
    prompts: [
      { label: l("Revelar", "Reveal"), text: "Continue the shot, the car keeps driving along the cliff road and the camera rises to reveal the sea at sunset" },
      { label: l("Seguir", "Follow"), text: "Continue seamlessly, the character keeps walking and turns the corner, handheld camera follows" },
      { label: l("Final", "Ending"), text: "Continue the shot and slowly pull back into a wide shot, fade the action to a calm ending" },
    ],
    tips: [
      l("Extiende varias veces seguidas para construir planos más largos.", "Extend a few times in a row to build longer shots."),
      l("Mantén las mismas palabras de estilo que el prompt original.", "Keep the same style words as the original prompt."),
    ],
  },
  {
    slug: "ugc-ad",
    title: l("Anuncio UGC sin rodar", "UGC ad without a shoot"),
    tagline: l("Un video vertical estilo «grabado con el móvil» de alguien que recomienda tu producto.", "A vertical, shot-on-phone style video of someone recommending your product."),
    category: "Product",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/object-swap.webp",
    model: "bytedance/seedance-2.5/reference-to-video",
    sample: { prompt: "cost preview", image_urls: ["https://example.com/a.png"], duration: 10, resolution: "480p", aspect_ratio: "9:16" },
    uiHref: studioHref("video", "create", "references", "bytedance/seedance-2.5/reference-to-video"),
    ui: [
      { title: l("Abre Video › Referencias con Seedance 2.5", "Open Video › References with Seedance 2.5"), body: l("Añade la foto del producto y, si quieres, la de la persona y la del lugar. Seedance 2.5 admite hasta 30 imágenes.", "Add the product photo and, if you want, the person and the location. Seedance 2.5 takes up to 30 images.") },
      { title: l("Escribe el guion dentro del prompt", "Put the script inside the prompt"), body: l("Gancho en la primera frase, lo que dice entre comillas y cómo sostiene el producto. Pide el look de móvil: cámara en mano, luz de ventana, sin música.", "Hook in the first line, what they say in quotes and how they hold the product. Ask for the phone look: handheld, window light, no music.") },
      { title: l("9:16, 10 s y 480p para probar", "9:16, 10 s and 480p to test"), body: l("Deja el audio activado: Seedance genera la voz y el sonido del ambiente.", "Keep audio on: Seedance generates the voice and the room sound.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Saca 3 o 4 ganchos distintos con el mismo producto y quédate con el que más retenga.", "Make 3 or 4 different hooks with the same product and keep the one that holds attention best.") },
    ],
    ask: l(
      "Con ./producto.png haz tres anuncios UGC verticales de 10 s, cada uno con un gancho distinto, estilo grabado con el móvil y voz en español. Cotiza el lote antes de generar.",
      "Using ./product.png make three 10 s vertical UGC ads, each with a different hook, shot-on-phone style with English voice. Quote the batch before generating.",
    ),
    mcp: [
      { title: l("Sube el producto", "Upload the product"), tool: "upload_media" },
      { title: l("Escribe los ganchos", "Write the hooks"), body: l("El agente redacta tres guiones cortos (gancho, beneficio, cierre) y los mete en el prompt.", "The agent writes three short scripts (hook, benefit, close) and puts them in the prompt.") },
      { title: l("Cotiza el lote", "Quote the batch"), body: l("Un ítem por gancho, con la misma referencia de producto.", "One item per hook, same product reference."), tool: "generate_batch (dry_run)" },
      { title: l("Genera con tu OK y descarga", "Generate on your OK and download"), tool: "generate_batch → wait_generations → download_outputs" },
    ],
    prompts: [
      { label: l("Reseña en la cocina", "Kitchen review"), text: "Authentic UGC smartphone talking-head video, vertical. A young woman in her kitchen holds the product from the reference image up to the camera and says: \"Nobody tells you this about cold brew.\" Handheld phone camera, natural window light, she blinks naturally and moves like a real filmed person, five fingers on every hand, room sound only, no music" },
      { label: l("Unboxing POV", "POV unboxing"), text: "Vertical POV unboxing video, camera fixed like a phone on a stand, hands enter the frame and open a cardboard box revealing the product from the reference image, soft daylight, slow, calm and ASMR-like pacing, paper and box sounds only" },
      { label: l("Antes y después", "Before and after"), text: "Vertical selfie video of a man showing the product from the reference image, he says: \"Two weeks ago I didn't believe this either.\" Bathroom mirror light, slight handheld shake, casual tone, ambient sound, no music" },
    ],
    tips: [
      l("Higgsfield recomienda varias piezas cortas en vez de un video largo: prueba ganchos, no duraciones.", "Higgsfield recommends several short pieces over one long video: test hooks, not lengths."),
      l("Frases como «five fingers on every hand» o «moves like a real filmed person» reducen los fallos de manos y de rigidez.", "Lines like “five fingers on every hand” or “moves like a real filmed person” reduce hand glitches and stiffness."),
      l("Pon entre comillas lo que dice y en qué idioma: Seedance genera la voz con el video.", "Quote what they say and in which language: Seedance generates the voice with the video."),
    ],
  },
  {
    slug: "product-ad-image",
    title: l("Foto de producto lista para anuncio", "Ad-ready product photo"),
    tagline: l("Pon tu producto real en una escena de campaña sin estudio de fotos, con Marketing Studio.", "Place your real product in a campaign scene without a photo studio, with Marketing Studio."),
    category: "Product",
    output: "image",
    channels: ["ui", "mcp"],
    art: "/art/image-edit.webp",
    model: "marketing-studio/image",
    sample: { prompt: "cost preview", image_urls: ["https://example.com/a.png"], resolution: "2k", aspect_ratio: "3:4" },
    uiHref: studioHref("image", "create", "edit", "marketing-studio/image"),
    ui: [
      { title: l("Abre Imagen › Editar imagen", "Open Image › Edit image"), body: l("Elige Marketing Studio en el selector de modelo y sube la foto del producto (mejor sobre fondo liso).", "Pick Marketing Studio in the model chip and upload the product photo (ideally on a plain background).") },
      { title: l("Describe la escena", "Describe the scene"), body: l("Superficie, luz, ambiente y formato del anuncio. Di que el producto no cambia: forma, etiqueta y colores.", "Surface, light, mood and ad format. Say the product must not change: shape, label and colors.") },
      { title: l("Formato y resolución", "Format and resolution"), body: l("3:4 o 4:5 para el feed, 9:16 para historias. 2K basta para redes.", "3:4 or 4:5 for the feed, 9:16 for stories. 2K is enough for social.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Desde la Biblioteca, «Usar en…» la lleva a Video para animarla.", "From the Library, “Use in…” takes it to Video to animate it.") },
    ],
    ask: l(
      "Con ./lata.png crea tres imágenes de anuncio: sobre hielo picado, en una mesa de picnic al atardecer y flotando con gotas de agua. 3:4, sin texto. Cotiza primero.",
      "Using ./can.png create three ad images: on crushed ice, on a picnic table at sunset and floating with water droplets. 3:4, no text. Quote first.",
    ),
    mcp: [
      { title: l("Sube el producto", "Upload the product"), tool: "upload_media" },
      { title: l("Lee las notas del modelo", "Read the model notes"), body: l("Marketing Studio acepta hasta 16 imágenes de referencia.", "Marketing Studio takes up to 16 reference images."), tool: "get_model" },
      { title: l("Cotiza las escenas", "Quote the scenes"), tool: "generate_batch (dry_run)" },
      { title: l("Genera con tu OK y descarga", "Generate on your OK and download"), tool: "generate_batch → wait_generations → download_outputs" },
    ],
    prompts: [
      { label: l("Hielo", "Ice"), text: "The product from the reference image resting on crushed ice, condensation droplets, cold blue rim light, dark background, commercial beverage photography, keep the product shape, label and colors exactly the same, no text" },
      { label: l("Picnic", "Picnic"), text: "The product from the reference image on a wooden picnic table at golden hour, blurred friends laughing in the background, warm lifestyle campaign photo, keep the label unchanged, no text" },
      { label: l("Flotando", "Floating"), text: "The product from the reference image floating in mid air with water splashes frozen around it, bright seamless color background, high-speed flash photography, keep the label unchanged, no text" },
    ],
    tips: [
      l("Pide siempre que la etiqueta y los colores no cambien: es lo que más se deforma.", "Always ask to keep the label and colors unchanged: it is what distorts most."),
      l("Para muchas variantes, cambia solo la escena y deja igual el resto del prompt.", "For many variants, change only the scene and keep the rest of the prompt the same."),
    ],
  },
  {
    slug: "director-scene",
    title: l("Escena con controles de director", "Scene with director controls"),
    tagline: l("Género, lente, cámara, época y paleta de color como en un set, con Cinema Studio 4.0.", "Genre, lens, camera, era and color palette like on set, with Cinema Studio 4.0."),
    category: "Cinematic",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/text-to-video.webp",
    model: "higgsfield/cinema-studio/4.0",
    sample: { prompt: "cost preview", duration: 5, resolution: "480p", aspect_ratio: "21:9", genre: "noir", camera_lens: "anamorphic", generate_audio: false },
    uiHref: studioHref("video", "create", "references", "higgsfield/cinema-studio/4.0"),
    ui: [
      { title: l("Abre Video › Referencias con Cinema Studio 4.0", "Open Video › References with Cinema Studio 4.0"), body: l("Sin referencias funciona como texto a video; con imágenes, videos o audio usa tus referencias (hasta 30 imágenes).", "Without references it works as text to video; with images, videos or audio it follows your references (up to 30 images).") },
      { title: l("Elige los controles", "Pick the controls"), body: l("Género, época, cámara (35 mm, 8 mm, DV), lente, apertura, movimiento (dolly, crane, bullet time…), luz, ritmo y una de sus 50 paletas. Deja vacío lo que quieras que decida el director.", "Genre, era, camera (35mm, 8mm, DV), lens, aperture, move (dolly, crane, bullet time…), light, pacing and one of its 50 palettes. Leave empty whatever you want the director to choose.") },
      { title: l("Escribe solo la acción", "Write only the action"), body: l("Quién, dónde y qué pasa. El estilo ya lo ponen los controles.", "Who, where and what happens. The controls already set the style.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Hasta 30 s por clip. Prueba con 5 s a 480p.", "Up to 30 s per clip. Test with 5 s at 480p.") },
    ],
    ask: l(
      "Hazme una escena noir de 8 s en 21:9: un detective enciende un cigarro bajo la lluvia. Lente anamórfica, cámara de 35 mm, dolly-in, época de los 60. Cotiza primero.",
      "Make me an 8 s noir scene in 21:9: a detective lights a cigarette in the rain. Anamorphic lens, 35mm film camera, dolly-in, 1960s. Quote first.",
    ),
    mcp: [
      { title: l("Lee los controles", "Read the controls"), body: l("El agente ve los valores válidos de género, lente, movimiento y paleta.", "The agent sees the valid values for genre, lens, move and palette."), tool: "get_model" },
      { title: l("Cotiza", "Quote"), tool: "estimate_cost" },
      { title: l("Genera con tu OK", "Generate on your OK"), tool: "generate → get_generation" },
      { title: l("Descarga", "Download"), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("Detective noir", "Noir detective"), text: "A detective in a wet trench coat lights a cigarette under a flickering street lamp, rain pouring, he looks up as a car passes" },
      { label: l("Cocina de los 80", "80s kitchen"), text: "A family argues around a small kitchen table, the youngest kid quietly steals the last pancake" },
      { label: l("Persecución", "Chase"), text: "A courier on a bicycle weaves through traffic in a crowded market, chased by two men on foot" },
    ],
    tips: [
      l("No escribas «auto»: deja el campo vacío para que el director elija.", "Don't write “auto”: leave the field empty and the director chooses."),
      l("Para citar una referencia en el prompt usa <<<image_1>>>, <<<video_1>>>…", "To cite a reference in the prompt use <<<image_1>>>, <<<video_1>>>…"),
    ],
  },
  {
    slug: "asset-first-spot",
    title: l("Spot cinematográfico con hojas de referencia", "Cinematic spot from reference sheets"),
    tagline: l("Primero personaje, producto y lugar sobre fondo gris; luego el plano con un prompt por bloques.", "First the character, product and location on a grey backdrop; then the shot with a block prompt."),
    category: "Cinematic",
    output: "video",
    channels: ["mcp", "ui"],
    art: "/art/references.webp",
    model: "bytedance/seedance-2.5/reference-to-video",
    sample: { prompt: "cost preview", image_urls: ["https://example.com/a.png", "https://example.com/b.png"], duration: 10, resolution: "720p", aspect_ratio: "16:9" },
    costNote: l("Solo el video. Las hojas de referencia son imágenes de céntimos y se cotizan antes.", "Video only. The reference sheets are cent-level images and are quoted first."),
    uiHref: studioHref("video", "create", "references", "bytedance/seedance-2.5/reference-to-video"),
    ui: [
      { title: l("Crea las hojas", "Make the sheets"), body: l("En Imagen, genera el personaje (frente, espalda, primer plano), el producto (frente, perfil, dorso) y el lugar, siempre «on a seamless neutral grey studio backdrop».", "In Image, generate the character (front, back, close-up), the product (front, side, back) and the location, always “on a seamless neutral grey studio backdrop”.") },
      { title: l("Llévalas a Referencias", "Take them to References"), body: l("Desde la Biblioteca, «Usar en…» › Referencia de video. Seedance 2.5 admite hasta 30 imágenes.", "From the Library, “Use in…” › Video reference. Seedance 2.5 takes up to 30 images.") },
      { title: l("Escribe el prompt por bloques", "Write a block prompt"), body: l("Contexto, referencias activas, cámara y óptica, acción segundo a segundo, luz y audio. Usa el prompt de abajo como plantilla.", "Context, active references, camera and optics, second-by-second action, light and audio. Use the prompt below as a template.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Hasta 30 s por clip. Repite el bloque de referencias en cada plano para mantener la coherencia.", "Up to 30 s per clip. Repeat the reference block in every shot to stay consistent.") },
    ],
    ask: l(
      "Quiero un spot de 15 s de un reloj de buceo: crea hojas de referencia del buzo, el reloj y un barco al amanecer sobre fondo gris, y luego el plano con Seedance 2.5 usando un prompt por bloques. Cotiza cada paso.",
      "I want a 15 s spot for a dive watch: create reference sheets of the diver, the watch and a boat at dawn on a grey backdrop, then the shot with Seedance 2.5 using a block prompt. Quote every step.",
    ),
    mcp: [
      { title: l("Cotiza y genera las hojas", "Quote and make the sheets"), body: l("Un ítem por hoja, con el mismo fondo gris.", "One item per sheet, same grey backdrop."), tool: "generate_batch → wait_generations" },
      { title: l("Encadena las salidas", "Chain the outputs"), body: l("Toma la URL de cada hoja sin descargarla.", "Takes each sheet's URL without downloading it."), tool: "use_output" },
      { title: l("Escribe y cotiza el plano", "Write and quote the shot"), body: l("El agente arma el prompt por bloques y lo cotiza con las referencias.", "The agent builds the block prompt and quotes it with the references."), tool: "estimate_cost" },
      { title: l("Genera con tu OK", "Generate on your OK"), tool: "generate → get_generation → download_outputs" },
    ],
    prompts: [
      { label: l("Hoja de personaje", "Character sheet"), text: "Character reference sheet of a professional diver in a black wetsuit: full-body front view, back view and head close-up, on a seamless neutral grey studio backdrop, even soft light, photoreal" },
      { label: l("Prompt por bloques", "Block prompt"), text: "SCENE CONTEXT: 15 s premium spot for a dive watch. ACTIVE REFERENCES: image 1 is the diver, image 2 is the watch, image 3 is the boat. OPTICS: 35mm, Kodak 500T look, handheld with organic shake. ACTION TIMING: 0-4 s the diver checks the watch on the deck at dawn; 4-9 s he rolls backwards into the sea; 9-15 s underwater close-up of the watch glowing. PHYSICS: real water splashes and bubbles. LIGHTING: low warm sun, then cold blue underwater. AUDIO: SFX only, no score. LOCKS: no CGI, photoreal only, the watch keeps its exact design" },
    ],
    tips: [
      l("Es la receta de los anuncios de coches y cortos 4K del blog de Higgsfield: los assets sobre gris fijan la identidad.", "It's the recipe behind the car commercials and 4K shorts on Higgsfield's blog: grey-backdrop assets lock the identity."),
      l("Pídele a tu agente que escriba el bloque ACTION TIMING segundo a segundo: es lo que más controla el resultado.", "Ask your agent to write the ACTION TIMING block second by second: it controls the result the most."),
    ],
  },
  {
    slug: "kling-elements",
    title: l("Personaje recurrente con elementos de Kling", "Recurring character with Kling elements"),
    tagline: l("Guarda un personaje o producto una vez y cítalo como @nombre en todos tus videos de Kling 3.0.", "Save a character or product once and cite it as @name in all your Kling 3.0 videos."),
    category: "Cinematic",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/frames.webp",
    model: "kling-video/v3.0/std/image-to-video",
    sample: { prompt: "cost preview", image_url: "https://example.com/a.png", duration: 5, sound: "off" },
    uiHref: studioHref("video", "create", "references", "kling-video/v3.0/std/image-to-video"),
    ui: [
      { title: l("Crea el elemento", "Create the element"), body: l("En Elementos, sube de 2 a 4 fotos JPG o PNG del personaje o producto y ponle un nombre corto.", "In Elements, upload 2 to 4 JPG or PNG photos of the character or product and give it a short name.") },
      { title: l("Úsalo en el estudio", "Use it in the studio"), body: l("Desde el elemento, «Usar en el estudio» abre Kling 3.0 con él elegido (hasta 3 por video).", "From the element, “Use in the studio” opens Kling 3.0 with it selected (up to 3 per video).") },
      { title: l("Cítalo en el prompt", "Cite it in the prompt"), body: l("Escribe @nombre donde aparece. Añade el fotograma inicial: Kling 3.0 parte de una imagen.", "Write @name where it appears. Add the start frame: Kling 3.0 starts from an image.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Los elementos salen solo por APIMart o KIE, que suelen ser más baratos que Higgsfield.", "Elements run only on APIMart or KIE, which are usually cheaper than Higgsfield.") },
    ],
    ask: l(
      "Crea un elemento «mila» con las fotos de ./mila y haz un video de 5 s con Kling 3.0 donde @mila pasea por un mercado, partiendo de ./mercado.png. Cotiza primero.",
      "Create an element “mila” with the photos in ./mila and make a 5 s Kling 3.0 video where @mila walks through a market, starting from ./market.png. Quote first.",
    ),
    mcp: [
      { title: l("Crea el elemento", "Create the element"), body: l("Con 2 a 4 imágenes; devuelve un id el_…", "With 2 to 4 images; returns an el_… id."), tool: "create_element" },
      { title: l("Sube el fotograma inicial", "Upload the start frame"), tool: "upload_media" },
      { title: l("Cotiza", "Quote"), body: l("Pone el id en elements y cita @mila en el prompt; compara APIMart y KIE.", "Puts the id in elements and cites @mila in the prompt; compares APIMart and KIE."), tool: "estimate_cost" },
      { title: l("Genera con tu OK", "Generate on your OK"), tool: "generate → get_generation → download_outputs" },
      { title: l("Reutilízalo", "Reuse it"), body: l("El elemento queda guardado para los siguientes videos.", "The element stays saved for the next videos."), tool: "list_elements" },
    ],
    prompts: [
      { label: l("Mercado", "Market"), text: "@mila walks through a busy fruit market, picks up an orange and smiles at the vendor, handheld camera following at shoulder height" },
      { label: l("Producto en mano", "Product in hand"), text: "@mila holds @bottle up to the camera in a sunny park and takes a sip, slow push-in" },
      { label: l("Multiplano", "Multi-shot"), text: "Wide shot of @mila entering a café, then medium shot of her ordering at the counter, then close-up of her first sip" },
    ],
    tips: [
      l("Las fotos del elemento con ángulos distintos (frente, perfil, cuerpo entero) dan más coherencia.", "Element photos from different angles (front, side, full body) give more consistency."),
      l("Con multi_shots, Kling 3.0 hace hasta 6 planos en una sola generación.", "With multi_shots, Kling 3.0 makes up to 6 shots in a single generation."),
    ],
  },
  {
    slug: "genjutsu-recast",
    title: l("Cambia el reparto de un video", "Recast a video"),
    tagline: l("Conserva el movimiento, la cámara y el ritmo de un clip y cambia quién sale y dónde.", "Keep a clip's motion, camera and timing, and change who is in it and where."),
    category: "Motion",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/motion.webp",
    model: "higgsfiled/genjutsu/motion-transfer/v1.0",
    sample: { video_url: "https://example.com/a.mp4", image_urls: ["https://example.com/a.png"], resolution: "480p" },
    uiHref: studioHref("video", "genjutsu", "motion", "higgsfiled/genjutsu/motion-transfer/v1.0"),
    ui: [
      { title: l("Abre Genjutsu › Transferir movimiento", "Open Genjutsu › Motion transfer"), body: l("Sube el clip original, de 4 a 30 s.", "Upload the original clip, 4 to 30 s.") },
      { title: l("Añade el nuevo reparto", "Add the new cast"), body: l("Hasta 8 imágenes: personajes, lugar o vestuario.", "Up to 8 images: characters, location or wardrobe.") },
      { title: l("Prompt opcional", "Optional prompt"), body: l("Úsalo para el estilo (anime, live-action, otra época). Vacío también funciona.", "Use it for the style (anime, live-action, another era). Empty works too.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Se cobra por la duración del clip: recórtalo al mejor tramo.", "It's priced by the clip length: trim it to the best part.") },
    ],
    ask: l(
      "Toma ./baile.mp4 y rehazlo con el personaje de ./robot.png en una azotea al atardecer, conservando el movimiento. 480p. Cotiza con la duración real.",
      "Take ./dance.mp4 and redo it with the character in ./robot.png on a rooftop at sunset, keeping the motion. 480p. Quote with the real length.",
    ),
    mcp: [
      { title: l("Sube el clip y el reparto", "Upload the clip and the cast"), tool: "upload_media" },
      { title: l("Cotiza con la duración", "Quote with the length"), tool: "estimate_cost (input_video_seconds)" },
      { title: l("Genera con tu OK", "Generate on your OK"), tool: "generate → get_generation" },
      { title: l("Descarga", "Download"), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("De live-action a anime", "Live-action to anime"), text: "Recreate the scene as a hand drawn anime with the character from the reference, keep every movement and the camera" },
      { label: l("Cambio de vestuario", "Wardrobe change"), text: "Same person and motion, now wearing the outfit from the reference image, keep lighting and camera" },
      { label: l("Otro mercado", "Another market"), text: "Recast the ad with the person from the reference image in a Tokyo street at night, keep the timing of every gesture" },
    ],
    tips: [
      l("Higgsfield lo usa para adaptar un mismo anuncio a otros mercados sin volver a rodar.", "Higgsfield uses it to adapt one ad to other markets without reshooting."),
      l("Si solo quieres cambiar un objeto, usa el Multiplicador de anuncios (Cambiar objetos).", "If you only want to swap one object, use the Ad multiplier (Objects swap)."),
    ],
  },
  {
    slug: "image-edit",
    title: l("Edita una foto con instrucciones", "Edit a photo with instructions"),
    tagline: l("Cambia el fondo, la ropa o un texto de una foto con una frase, sin máscaras.", "Change the background, the outfit or a text in a photo with one sentence, no masks."),
    category: "Edit",
    output: "image",
    channels: ["ui", "mcp"],
    art: "/art/video-edit.webp",
    model: "alibaba/qwen-image-3/edit",
    sample: { prompt: "cost preview", image_urls: ["https://example.com/a.png"], resolution: "1k" },
    uiHref: studioHref("image", "create", "edit", "alibaba/qwen-image-3/edit"),
    ui: [
      { title: l("Abre Imagen › Editar imagen", "Open Image › Edit image"), body: l("Sube la foto. Puedes añadir hasta 2 referencias más (una prenda, un logo).", "Upload the photo. You can add up to 2 more references (a garment, a logo).") },
      { title: l("Da una instrucción directa", "Give a direct instruction"), body: l("«Cambia el fondo por…», «Reemplaza la camiseta por…». Di qué debe quedar igual.", "“Change the background to…”, “Replace the T-shirt with…”. Say what must stay the same.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Cuesta céntimos: itera hasta que quede bien y luego anímala.", "It costs cents: iterate until it's right, then animate it.") },
    ],
    ask: l(
      "Edita ./retrato.jpg: cambia el fondo por un café de París de noche y conserva la cara y la luz. Cotiza primero.",
      "Edit ./portrait.jpg: change the background to a Paris café at night and keep the face and the light. Quote first.",
    ),
    mcp: [
      { title: l("Sube la foto", "Upload the photo"), tool: "upload_media" },
      { title: l("Elige el modelo de edición", "Pick the edit model"), body: l("Qwen Image 3, Grok Imagine o Ideogram 4 editan imágenes.", "Qwen Image 3, Grok Imagine or Ideogram 4 can edit images."), tool: "find_models (edit)" },
      { title: l("Cotiza y genera con tu OK", "Quote and generate on your OK"), tool: "estimate_cost → generate → get_generation" },
      { title: l("Descarga", "Download"), tool: "download_outputs" },
    ],
    prompts: [
      { label: l("Fondo", "Background"), text: "Change the background to a Paris café at night with warm string lights, keep the person, the face and the lighting on the subject unchanged" },
      { label: l("Ropa", "Outfit"), text: "Replace the T-shirt with a black leather jacket, keep the pose, the face and the background" },
      { label: l("Texto del póster", "Poster text"), text: "Replace the headline on the poster with the text \"OPEN LATE\" in the same font style and color, keep everything else" },
    ],
    tips: [
      l("Una sola instrucción por edición: encadena varias en lugar de pedirlo todo a la vez.", "One instruction per edit: chain several instead of asking for everything at once."),
      l("Para colocar tu producto en una escena de anuncio, usa Marketing Studio.", "To place your product in an ad scene, use Marketing Studio."),
    ],
  },
  {
    slug: "talking-avatar",
    title: l("Un avatar que habla con tu guion", "An avatar that speaks your script"),
    tagline: l("Escribe el texto, elige una voz de ElevenLabs y haz que una foto lo diga.", "Write the text, pick an ElevenLabs voice and make a photo say it."),
    category: "Animate",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/text-to-image.webp",
    model: "wan/v2.7/image-to-video",
    sample: { prompt: "cost preview", image_url: "https://example.com/a.png", audio_url: "https://example.com/a.mp3", duration: 10, resolution: "720p" },
    costNote: l("Solo el video. La voz cuesta aparte (0,10 USD por 1.000 caracteres a precio de lista) y se cotiza antes.", "Video only. The voice is extra (0.10 USD per 1,000 characters at list price) and is quoted first."),
    uiHref: studioHref("video", "create", "frames", "wan/v2.7/image-to-video"),
    ui: [
      { title: l("Genera la voz", "Generate the voice"), body: l("En Audio › Texto a voz, escribe el guion y elige una voz. Descarga el MP3 desde la Biblioteca.", "In Audio › Text to speech, write the script and pick a voice. Download the MP3 from the Library.") },
      { title: l("Abre Video › Inicio y final con Wan 2.7", "Open Video › Start & End with Wan 2.7"), body: l("Sube la foto como fotograma inicial y el MP3 como audio: el video sigue esa voz.", "Upload the photo as the start frame and the MP3 as audio: the video follows that voice.") },
      { title: l("Ajusta la duración al audio", "Match the length to the audio"), body: l("Hasta 15 s por clip; divide guiones más largos.", "Up to 15 s per clip; split longer scripts.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("Si prefieres, Seedance 2.5 Referencias también acepta audio de referencia.", "If you prefer, Seedance 2.5 References also takes reference audio.") },
    ],
    ask: l(
      "Haz que ./presentadora.png diga este texto con una voz femenina cálida en español: «Hoy te enseño tres trucos para…». Cotiza la voz y el video antes de generar.",
      "Make ./host.png say this text with a warm female voice: “Today I'll show you three tricks to…”. Quote the voice and the video before generating.",
    ),
    mcp: [
      { title: l("Elige la voz", "Pick the voice"), tool: "list_voices" },
      { title: l("Cotiza y genera la voz", "Quote and make the voice"), tool: "text_to_speech → get_generation" },
      { title: l("Encadena el audio", "Chain the audio"), body: l("Toma la URL del MP3 sin descargarlo.", "Takes the MP3 URL without downloading it."), tool: "use_output" },
      { title: l("Sube la foto y cotiza el video", "Upload the photo and quote the video"), body: l("Wan 2.7 con image_url y audio_url.", "Wan 2.7 with image_url and audio_url."), tool: "upload_media → estimate_cost" },
      { title: l("Genera con tu OK", "Generate on your OK"), tool: "generate → get_generation → download_outputs" },
    ],
    prompts: [
      { label: l("Presentadora", "Host"), text: "The woman talks directly to the camera with natural lip movement matching the audio, small head nods and hand gestures, static medium shot, soft studio light" },
      { label: l("Mascota de marca", "Brand mascot"), text: "The cartoon mascot speaks to the camera with expressive mouth movement synced to the audio, bouncy friendly gestures, plain background" },
      { label: l("Voz (texto a voz)", "Voice (text to speech)"), text: "[excited] Today I'll show you three tricks to keep your plants alive. [pause] Number one is the one nobody tells you." },
    ],
    tips: [
      l("Con eleven_v4 y eleven_v3, etiquetas como [excited] o [whispers] cambian la interpretación.", "With eleven_v4 and eleven_v3, tags like [excited] or [whispers] change the delivery."),
      l("Funciona mejor una foto de frente, con la boca visible y cerrada.", "A front-facing photo with a visible, closed mouth works best."),
      l("La página Voces tiene voces gratis en español (edge-tts) para probar el guion antes de pagar.", "The Voices page has free Spanish voices (edge-tts) to test the script before paying."),
    ],
  },
  {
    slug: "soundtrack",
    title: l("Narración, música y efectos para tu video", "Narration, music and sound effects for your video"),
    tagline: l("Locución, música original y efectos de ElevenLabs, guardados en tu sonoteca para reutilizarlos.", "Voice-over, original music and sound effects from ElevenLabs, saved to your sound library for reuse."),
    category: "Audio",
    output: "audio",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/soundtrack.svg",
    model: "elevenlabs/music",
    audio: { service: "music", body: { prompt: "cost preview", seconds: 30, force_instrumental: true } },
    costNote: l("Solo una pista de música de 30 s. La narración y los efectos se cotizan aparte, antes de generarlos.", "One 30 s music track only. Narration and effects are quoted separately, before you generate them."),
    uiHref: "/audio?tab=music",
    ui: [
      { title: l("Busca primero en la Sonoteca", "Search the Sound library first"), body: l("Reutilizar un sonido que ya tienes es gratis.", "Reusing a sound you already have is free.") },
      { title: l("Música", "Music"), body: l("Audio › Música: género, tempo, ánimo e instrumentos. Marca instrumental si va a sonar una voz encima.", "Audio › Music: genre, tempo, mood and instruments. Tick instrumental if a voice will play on top.") },
      { title: l("Efectos", "Sound effects"), body: l("Audio › Efectos: describe el sonido en inglés, de 0,5 a 30 s; puede ser un bucle.", "Audio › Sound effects: describe the sound in English, 0.5 to 30 s; it can loop.") },
      { title: l("Narración", "Narration"), body: l("Audio › Texto a voz con una voz de ElevenLabs, o gratis con las voces en español de la página Voces.", "Audio › Text to speech with an ElevenLabs voice, or free with the Spanish voices on the Voices page.") },
      { title: l("Aísla la voz si hace falta", "Isolate the voice if needed"), body: l("Audio › Aislar voz quita el ruido y la música de una grabación.", "Audio › Voice isolator removes noise and music from a recording.") },
    ],
    ask: l(
      "Para mi video de 30 s de una heladería: busca en la sonoteca algo que sirva; si no, crea una música alegre instrumental de 30 s, un efecto de cuchara raspando helado y una locución en español con este guion. Cotiza todo antes.",
      "For my 30 s ice cream shop video: search the sound library for something that fits; if not, create a happy 30 s instrumental track, a spoon scraping ice cream effect and a voice-over with this script. Quote everything first.",
    ),
    mcp: [
      { title: l("Busca en la sonoteca", "Search the library"), body: l("Gratis: lo ya generado (o importado de ElevenLabs) se reutiliza.", "Free: anything already generated (or imported from ElevenLabs) is reused."), tool: "list_sounds" },
      { title: l("Cotiza y crea la música", "Quote and compose the music"), tool: "compose_music" },
      { title: l("Cotiza y crea el efecto", "Quote and make the effect"), tool: "sound_effect" },
      { title: l("Cotiza y crea la locución", "Quote and make the voice-over"), tool: "list_voices → text_to_speech" },
      { title: l("Descarga y etiqueta", "Download and label"), body: l("Guarda los MP3 y ponles categoría y etiquetas para encontrarlos después.", "Saves the MP3s and gives them a category and tags to find them later."), tool: "download_outputs → label_sound" },
    ],
    prompts: [
      { label: l("Música alegre", "Happy music"), text: "Upbeat summer pop instrumental, ukulele and claps, 110 bpm, bright and playful, clean ending" },
      { label: l("Tensión", "Tension"), text: "Dark cinematic underscore, low drones and slow heartbeat percussion, building tension, no melody" },
      { label: l("Efecto", "Sound effect"), text: "Metal spoon scraping frozen ice cream from a tub, close microphone, crisp" },
    ],
    tips: [
      l("Los efectos y la música funcionan mejor descritos en inglés.", "Effects and music work best described in English."),
      l("Todo lo que generas queda en la Sonoteca, clasificado solo, para el próximo video.", "Everything you generate lands in the Sound library, auto-classified, for the next video."),
    ],
  },
  {
    slug: "voice-swap",
    title: l("Cambia la voz de un video", "Change the voice in a video"),
    tagline: l("Otra voz con las mismas palabras, ritmo y emoción, en todo el clip o solo en un tramo; con efecto de monstruo o fantasma si quieres.", "Another voice with the same words, timing and emotion, in the whole clip or just a section; with a monster or ghost effect if you want."),
    category: "Audio",
    output: "video",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/voice-swap.svg",
    model: "elevenlabs/voice-changer",
    uiHref: "/voice",
    ui: [
      { title: l("Abre Voz", "Open Voice"), body: l("Sube un video o elige una generación de la Biblioteca.", "Upload a video or pick a generation from the Library.") },
      { title: l("Marca el tramo", "Mark the section"), body: l("Inicio y fin en segundos; vacío = todo el clip. Solo se cobra el tramo.", "Start and end in seconds; empty = the whole clip. Only the section is charged.") },
      { title: l("Elige la voz y el efecto", "Pick the voice and the effect"), body: l("Una voz de tu cuenta o de la biblioteca pública, y si quieres un efecto: grave, monstruo o fantasma.", "A voice from your account or the public library, and an optional effect: deep, monster or ghost.") },
      { title: l("Mira el costo y genera", "Check the cost and generate"), body: l("El precio aparece al cargar el video (0,12 USD por minuto a precio de lista).", "The price appears once the video is loaded (0.12 USD per minute at list price).") },
    ],
    ask: l(
      "En ./zombie.mp4, cambia la voz del segundo 3 al 9 por una voz grave con efecto de monstruo y deja un poco del audio original de fondo. Cotiza primero.",
      "In ./zombie.mp4, change the voice from second 3 to 9 to a deep voice with a monster effect and keep a little of the original audio underneath. Quote first.",
    ),
    mcp: [
      { title: l("Elige la voz", "Pick the voice"), tool: "list_voices" },
      { title: l("Cotiza el tramo", "Quote the section"), body: l("Sin quote_id devuelve el precio del tramo [start, end].", "Without quote_id it returns the price of the [start, end] section."), tool: "change_voice" },
      { title: l("Genera con tu OK", "Generate on your OK"), body: l("La misma llamada con el quote_id.", "The same call with the quote_id."), tool: "change_voice → get_generation" },
      { title: l("Descarga", "Download"), tool: "download_outputs" },
    ],
    prompts: [],
    tips: [
      l("Si la grabación tiene ruido o música, pásala antes por Aislar voz.", "If the recording has noise or music, run it through Voice isolator first."),
      l("Con original_volume entre 0,1 y 0,3 queda algo del audio original y suena más natural.", "With original_volume between 0.1 and 0.3 some of the original audio remains and it sounds more natural."),
    ],
  },
  {
    slug: "reel-covers",
    title: l("Portadas de reels en lote", "Reel covers in batch"),
    tagline: l("Una serie de portadas verticales para redes, con espacio para el titular.", "A set of vertical covers for social media, with room for the headline."),
    category: "Social",
    output: "image",
    channels: ["ui", "mcp"],
    art: "/art/use-cases/reel-covers.webp",
    model: "z-image/turbo",
    sample: { prompt: "cost preview", aspect_ratio: "9:16", resolution: "2k" },
    uiHref: studioHref("image", "create", "text", "z-image/turbo"),
    preset: "reel-cover",
    ui: [
      { title: l("Abre el preset Portada de reel", "Open the Reel cover preset"), body: l("O Imagen › Texto a imagen con un modelo rápido y 9:16.", "Or Image › Text to image with a fast model and 9:16.") },
      { title: l("Tema y ambiente", "Subject and mood"), body: l("Una portada por tema; mantén el mismo ambiente en toda la serie.", "One cover per subject; keep the same mood for the whole series.") },
      { title: l("Genera", "Generate"), body: l("Las imágenes cuestan céntimos: genera varias y elige.", "Images cost cents: generate several and pick.") },
    ],
    ask: l(
      "Haz 6 portadas de reels para mi cafetería, cinematográficas y sombrías, con espacio para un titular. Cotiza el lote.",
      "Make 6 reel covers for my coffee shop, moody cinematic, room for a headline. Quote the batch.",
    ),
    mcp: [
      { title: l("Planifica la serie", "Plan the series"), body: l("El agente escribe seis temas que encajen con tu marca.", "The agent writes six subjects that fit your brand.") },
      { title: l("Cotiza el lote", "Quote the batch"), tool: "generate_batch (dry_run)" },
      { title: l("Genera, espera y descarga", "Generate, wait, download"), body: l("Las seis de una vez en ./covers.", "All six in one go into ./covers."), tool: "generate_batch → wait_generations → download_outputs" },
    ],
    prompts: [
      { label: l("Arte latte", "Latte art"), text: "Vertical social media cover photo of a barista pouring latte art, moody cinematic, strong focal point, generous empty space in the upper third for a headline, no text" },
      { label: l("Chef", "Chef"), text: "Vertical cover photo of a chef plating a dish under a single warm lamp, dark background, space at the top for a title, no text" },
      { label: l("Corredora", "Runner"), text: "Vertical cover photo of a runner at dawn on an empty bridge, retro film look, sky filling the upper third, no text" },
    ],
    tips: [
      l("'no text' evita letras falsas en la imagen.", "'no text' avoids fake letters in the image."),
      l("Mismas palabras de ambiente = una cuadrícula coherente en tu perfil.", "Same mood words = consistent grid on your profile."),
    ],
  },
  {
    slug: "storyboard",
    title: l("Storyboard a partir de un guion", "Storyboard from a script"),
    tagline: l("Tu agente divide un guion en planos y genera un fotograma para cada uno.", "Your agent breaks a script into shots and generates a frame for each one."),
    category: "Agents",
    output: "image",
    channels: ["mcp"],
    art: "/art/use-cases/storyboard.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "16:9", resolution: "1080p" },
    ask: l(
      "Lee ./guion.md, divídelo en 6 planos y genera un fotograma 16:9 para cada uno con el mismo estilo visual. Cotiza primero el lote y guárdalos en ./storyboard.",
      "Read ./script.md, split it into 6 shots and generate a 16:9 frame for each with the same visual style. Quote the batch first and save them to ./storyboard.",
    ),
    mcp: [
      { title: l("Lee el guion", "Read the script"), body: l("El agente lee el archivo y escribe una descripción de plano por momento (tamaño de plano, acción, luz).", "The agent reads the file and writes one shot description per beat (shot size, action, light).") },
      { title: l("Elige un modelo", "Pick a model"), body: l("Pide el mejor modelo de texto a imagen para fotogramas de película coherentes.", "Asks for the best text-to-image model for consistent film stills."), tool: "recommend_models" },
      { title: l("Cotiza todos los fotogramas", "Quote all frames"), body: l("Un ítem del lote por plano, con el mismo sufijo de estilo.", "One batch item per shot, same style suffix."), tool: "generate_batch (dry_run)" },
      { title: l("Genera y recoge", "Generate and collect"), body: l("Espera a todos y guarda shot-01.png … shot-06.png.", "Waits for all and saves shot-01.png … shot-06.png."), tool: "wait_generations → download_outputs" },
      { title: l("Anima los mejores", "Animate the keepers"), body: l("Opcional: convierte los fotogramas elegidos en clips de 5 s con imagen a video, cotizados otra vez.", "Optional: turns chosen frames into 5 s clips with image-to-video, quoted again.") },
    ],
    prompts: [
      { label: l("Sufijo de estilo", "Style suffix"), text: "cinematic film still, anamorphic, muted teal and orange palette, 35mm grain" },
      { label: l("Línea de plano", "Shot line"), text: "Wide shot: an astronaut crosses a red desert plain at dusk, tiny against the landscape" },
      { label: l("Primer plano", "Close-up"), text: "Extreme close-up: a glowing blue flower reflected in the astronaut's visor" },
    ],
    tips: [
      l("Dale al agente un único sufijo de estilo para todos los fotogramas.", "Give the agent one shared style suffix for all frames."),
      l("Pide tamaños de plano (general, medio, primer plano) para lograr el ritmo de un storyboard real.", "Ask for shot sizes (wide, medium, close-up) to get a real storyboard rhythm."),
    ],
  },
  {
    slug: "agent-assets",
    title: l("Recursos para tu código", "Assets for your codebase"),
    tagline: l("Mientras programas, tu agente genera las imágenes que necesita una página y las deja en el repo.", "While coding, your agent generates the images a page needs and drops them into the repo."),
    category: "Agents",
    output: "image",
    channels: ["mcp"],
    art: "/art/use-cases/agent-assets.webp",
    model: "higgsfield-ai/soul/v2/standard",
    sample: { prompt: "cost preview", aspect_ratio: "16:9", resolution: "1080p" },
    ask: l(
      "Esta landing necesita una imagen hero y tres ilustraciones de funcionalidades. Genéralas con nuestro estilo, cotiza primero, guárdalas en public/art como WebP y conéctalas a la página.",
      "This landing page needs a hero image and three feature illustrations. Generate them in our style, quote first, save to public/art as WebP and wire them into the page.",
    ),
    mcp: [
      { title: l("Lee la página", "Read the page"), body: l("El agente mira los componentes para ver qué imágenes faltan y sus proporciones.", "The agent looks at the components to see which images are missing and their aspect ratios.") },
      { title: l("Cotiza el conjunto", "Quote the set"), tool: "generate_batch (dry_run)" },
      { title: l("Genera con tu OK", "Generate on your OK"), tool: "generate_batch → wait_generations" },
      { title: l("Guárdalas en el repo", "Save into the repo"), body: l("Descarga en public/art, convierte a WebP y edita el JSX para usarlas.", "Downloads to public/art, converts to WebP and edits the JSX to use them."), tool: "download_outputs" },
      { title: l("Reutiliza la receta", "Reuse the recipe"), body: l("Guarda el estilo como preset para la próxima página.", "Saves the style as a preset for the next page."), tool: "save_preset" },
    ],
    prompts: [
      { label: l("Hero", "Hero"), text: "Wide hero image for a coffee shop website, warm morning light over the counter, shallow depth of field, space on the left for a headline" },
      { label: l("Funcionalidad", "Feature"), text: "Minimal still life of coffee beans and a ceramic cup on linen, top light, soft shadows, square crop" },
      { label: l("Equipo", "Team"), text: "Candid photo of two baristas laughing behind the counter, natural light, editorial style" },
    ],
    tips: [
      l("Dile al agente los tamaños exactos que espera el diseño.", "Tell the agent the exact sizes the layout expects."),
      l("Los resultados se copian en local, así que los enlaces nunca caducan.", "Outputs are copied locally, so links never expire."),
    ],
  },
];

export const CATEGORIES: Category[] = [...new Set(USE_CASES.map((u) => u.category))];
