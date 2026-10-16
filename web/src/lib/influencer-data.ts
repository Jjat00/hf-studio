/**
 * Catálogo de AI Influencer copiado de Higgsfield (MCP `ai_influencer_get_options` y `ai_influencer_list_presets`,
 * a 2026-10-13): los mismos tipos de personaje, grupos de rasgos con sus restricciones por tipo, y los ejemplos de
 * su galería con su selección, brief y semilla. Las miniaturas se enlazan desde el CDN público de Higgsfield.
 */

export const CDN = "https://static-public-media.higgsfield.ai/ai-influencer-explore-presets/";

export type Tier = "normal" | "freak" | "total" | "insects" | "frogs" | "cats" | "dogs" | "capybaras" | "birds";

export const ANIMALS: Tier[] = ["insects", "frogs", "cats", "dogs", "capybaras", "birds"];

export const TIERS: { id: Tier; es: string; en: string; emoji: string }[] = [
  { id: "normal", es: "Normal", en: "Average", emoji: "🙂" },
  { id: "freak", es: "Atrevido", en: "Bold", emoji: "😎" },
  { id: "total", es: "Extremo", en: "Extreme", emoji: "🤪" },
  { id: "insects", es: "Insecto", en: "Insect", emoji: "🪲" },
  { id: "frogs", es: "Rana", en: "Frog", emoji: "🐸" },
  { id: "cats", es: "Gato", en: "Cat", emoji: "🐱" },
  { id: "dogs", es: "Perro", en: "Dog", emoji: "🐶" },
  { id: "capybaras", es: "Roedor", en: "Rodent", emoji: "🐹" },
  { id: "birds", es: "Ave", en: "Bird", emoji: "🐦" },
];

/** Para qué tipos vale una opción: a = todos, fa = atrevido, extremo y animales, h = humanos, ft = atrevido y extremo, t = extremo, ta = extremo y animales. */
type Scope = "a" | "fa" | "h" | "ft" | "t" | "ta";
const SCOPES: Record<Scope, Tier[]> = {
  a: ["normal", "freak", "total", ...ANIMALS],
  fa: ["freak", "total", ...ANIMALS],
  h: ["normal", "freak", "total"],
  ft: ["freak", "total"],
  t: ["total"],
  ta: ["total", ...ANIMALS],
};

/** Miniaturas propias (generadas con Codex) para los tipos y los grupos visuales, como las tarjetas de Higgsfield. */
export const thumb = (id: string) => `/art/influencer/${id}.webp`;
export const tierThumb = (tier: Tier) => `/art/influencer/tier-${tier}.webp`;
export const IMAGE_GROUPS = new Set(["body_type", "hair", "aesthetic", "facial_hair", "accessory"]);
/** Muestras de color para los grupos que son colores. */
export const SWATCH: Record<string, string> = {
  hc_black: "#0b0b0c", hc_darkbrown: "#3b2416", hc_chestnut: "#6b3a1f", hc_ginger: "#c25a1c", hc_red: "#a3161f",
  hc_blonde: "#d9b766", hc_platinum: "#ece6d6", hc_grey: "#9a9a9a", hc_white: "#f4f4f2", hc_pink: "#f2a7c3",
  hc_lilac: "#b9a2e0", hc_blue: "#2f6fd6", hc_green: "#3e9d4e",
  st_porcelain: "#f6e3d7", st_fair: "#efd2bd", st_light: "#e3bb9c", st_olive: "#c69c6d", st_tan: "#b07d52",
  st_brown: "#8b5a3c", st_deep: "#5e3a26", st_ebony: "#3a2418",
  eye_black: "#151212", eye_brown: "#5b3a1e", eye_hazel: "#8e6b33", eye_green: "#4f7d3a", eye_blue: "#3d77c2",
  eye_ice_blue: "#a8d4ef", eye_amber: "#c2862a", eye_grey: "#8c959c",
};

export type Option = { id: string; en: string; es: string; tiers: Tier[] };
export type Group = { id: string; es: string; en: string; max: number; prompt: string; options: Option[] };

const g = (id: string, es: string, en: string, max: number, prompt: string, opts: [string, string, string, Scope][]): Group => ({
  id,
  es,
  en,
  max,
  prompt,
  options: opts.map(([oid, oen, oes, scope]) => ({ id: oid, en: oen, es: oes, tiers: SCOPES[scope] })),
});

export const GROUPS: Group[] = [
  g("gender", "Género", "Gender", 1, "gender", [
    ["female", "Female", "Mujer", "a"],
    ["male", "Male", "Hombre", "a"],
    ["trans_man", "Trans man", "Hombre trans", "a"],
    ["trans_woman", "Trans woman", "Mujer trans", "a"],
    ["non_binary", "Non-binary", "No binario", "a"],
  ]),
  g("body_type", "Complexión", "Build", 1, "build", [
    ["body_slim", "Slim", "Delgada", "a"],
    ["body_athletic", "Athletic", "Atlética", "a"],
    ["body_hourglass", "Hourglass", "Curvilínea", "a"],
    ["body_muscular", "Muscular", "Musculosa", "a"],
    ["body_curvy", "Curvy", "Con curvas", "a"],
    ["body_heavy", "Heavy", "Robusta", "a"],
    ["body_ultra", "Ultra Muscular", "Ultra musculosa", "a"],
    ["pr_centaur", "Centaur", "Centauro", "ta"],
  ]),
  g("hair", "Peinado", "Hairstyle", 1, "hairstyle", [
    ["hs_lampshade", "Bob", "Bob", "fa"],
    ["hair_bald", "Bald", "Calvo", "a"],
    ["hair_buzz", "Buzz cut", "Rapado", "a"],
    ["hair_bowl", "Bowl cut", "Corte tazón", "a"],
    ["hair_mullet", "Mullet", "Mullet", "a"],
    ["hair_braids", "Braids", "Trenzas", "a"],
    ["hair_pigtails", "Pigtails", "Coletas", "a"],
    ["hair_afro", "Afro", "Afro", "a"],
    ["hair_punk", "Mohawk", "Cresta", "a"],
    ["hs_pompadour", "Volume waves", "Ondas con volumen", "fa"],
    ["hs_beehive", "Beehive", "Colmena", "fa"],
    ["hs_dome", "Perm", "Permanente", "fa"],
    ["hair_long", "Long hair", "Pelo largo", "a"],
    ["hair_short", "Short hair", "Pelo corto", "a"],
    ["hs_horns", "Hair horns", "Cuernos de pelo", "fa"],
    ["hs_softserve", "Soft-serve swirl", "Remolino de helado", "fa"],
    ["hs_sphere", "Curl sphere", "Esfera de rizos", "fa"],
    ["hs_mouse", "Mouse-ear puffs", "Orejas de ratón", "fa"],
    ["hs_wings", "Hair wings", "Alas de pelo", "fa"],
    ["hs_hedgehog", "Hedgehog spikes", "Pinchos de erizo", "fa"],
    ["hs_tufts", "Side tufts", "Mechones laterales", "fa"],
    ["hs_stairs", "Stair steps", "Escalones", "fa"],
    ["hs_shelf", "Shelf bob", "Bob en repisa", "fa"],
    ["hs_corkscrews", "Corkscrews", "Tirabuzones", "fa"],
    ["hs_sidecoil", "Side coil", "Espiral lateral", "fa"],
    ["hs_mushroom", "Mushroom", "Champiñón", "fa"],
  ]),
  g("hair_colour", "Color de pelo", "Hair Color", 1, "hair color", [
    ["hc_black", "Jet black", "Negro azabache", "a"],
    ["hc_darkbrown", "Dark brown", "Castaño oscuro", "a"],
    ["hc_chestnut", "Chestnut", "Castaño", "a"],
    ["hc_ginger", "Ginger", "Pelirrojo", "a"],
    ["hc_red", "Red", "Rojo", "a"],
    ["hc_blonde", "Blonde", "Rubio", "a"],
    ["hc_platinum", "Platinum", "Platino", "a"],
    ["hc_grey", "Grey", "Gris", "a"],
    ["hc_white", "White", "Blanco", "a"],
    ["hc_pink", "Pastel pink", "Rosa pastel", "a"],
    ["hc_lilac", "Lilac", "Lila", "a"],
    ["hc_blue", "Blue", "Azul", "a"],
    ["hc_green", "Green", "Verde", "a"],
  ]),
  g("aesthetic", "Estilo", "Style", 2, "style", [
    ["retro", "Retro", "Retro", "a"],
    ["sporty", "Sporty", "Deportivo", "a"],
    ["y2k", "Y2K", "Y2K", "a"],
    ["theatrical", "Theatre", "Teatral", "a"],
    ["goth", "Goth", "Gótico", "a"],
    ["suits", "Suits", "Trajes", "a"],
    ["streetstyle", "Streetstyle", "Urbano", "a"],
    ["casual", "Casual", "Casual", "a"],
    ["st_elegant", "Elegant", "Elegante", "a"],
    ["st_athlete", "Athlete", "Deportista", "a"],
    ["st_shorts", "Shorts", "Pantaloneta", "a"],
    ["st_tank", "Tank top", "Camisa esqueleto", "a"],
    ["st_long_skirt", "Long skirt", "Falda larga", "a"],
    ["st_mini_skirt", "Mini skirt", "Falda corta", "a"],
    ["st_bodycon", "Bodycon dress", "Vestido ajustado", "a"],
    ["st_flowy_dress", "Flowy dress", "Vestido suelto", "a"],
  ]),
  g("ethnicity_origin_base", "Origen", "Ethnicity", 1, "ethnicity", [
    ["african", "African", "Africano", "h"],
    ["east_asian", "Asian", "Asiático", "h"],
    ["european", "European", "Europeo", "h"],
    ["indian", "Indian", "Indio", "h"],
    ["middle_eastern", "Middle Eastern", "Oriente Medio", "h"],
    ["latin_american", "Mixed", "Mestizo", "h"],
  ]),
  g("age", "Edad", "Age", 1, "age", [
    ["adult", "Adult", "Adulto", "h"],
    ["mature", "Mature", "Maduro", "h"],
    ["senior", "Senior", "Mayor", "h"],
  ]),
  g("skin_tone", "Color de piel", "Skin color", 1, "skin tone", [
    ["st_porcelain", "Porcelain", "Porcelana", "h"],
    ["st_fair", "Fair", "Clara", "h"],
    ["st_light", "Light", "Blanca", "h"],
    ["st_olive", "Olive", "Oliva", "h"],
    ["st_tan", "Tan", "Bronceada", "h"],
    ["st_brown", "Brown", "Morena", "h"],
    ["st_deep", "Deep brown", "Morena oscura", "h"],
    ["st_ebony", "Ebony", "Ébano", "h"],
  ]),
  g("height", "Estatura", "Height", 1, "height", [
    ["h_average", "Average", "Media", "a"],
    ["h_tall", "Tall", "Alta", "a"],
    ["h_very_tall", "Very tall", "Muy alta", "a"],
  ]),
  g("proportions", "Proporciones", "Proportions", 2, "proportions", [
    ["pr_longlimbs", "Long limbs", "Extremidades largas", "a"],
    ["pr_shortlegs", "Short legs", "Piernas cortas", "a"],
    ["pr_shoulders", "Broad shoulders", "Hombros anchos", "a"],
    ["pr_waist", "Tiny waist", "Cintura diminuta", "a"],
    ["pr_egg", "Egg body", "Cuerpo de huevo", "fa"],
  ]),
  g("freak_head", "Forma de la cabeza", "Head shape", 1, "head shape", [
    ["head_oval", "Standard", "Normal", "h"],
    ["head_long", "Long", "Alargada", "h"],
    ["head_tiny", "Tiny", "Diminuta", "ft"],
    ["head_forehead", "High forehead", "Frente alta", "ft"],
    ["head_ancient", "Caveman", "Cavernícola", "t"],
    ["head_herojaw", "Gigachad", "Gigachad", "t"],
    ["head_megachin", "Mega jaw", "Mandíbula gigante", "t"],
    ["head_round", "Round", "Redonda", "h"],
    ["head_square", "Square", "Cuadrada", "h"],
    ["head_heart", "Heart", "Corazón", "h"],
  ]),
  g("freak_neck", "Cuello", "Neck", 1, "neck", [
    ["neck_normal", "Standard", "Normal", "h"],
    ["neck_column", "Column", "Columna", "ft"],
    ["neck_long", "Long", "Largo", "ft"],
    ["neck_short", "Short", "Corto", "h"],
  ]),
  g("eye_shape", "Forma de los ojos", "Eye shape", 1, "eye shape", [
    ["es_almond", "Almond", "Almendrados", "h"],
    ["es_round", "Round", "Redondos", "h"],
    ["es_monolid", "Monolid", "Monopárpado", "h"],
    ["es_close", "Close-set", "Juntos", "ft"],
    ["es_wide", "Wide-set", "Separados", "ft"],
    ["es_uneven", "Uneven", "Desiguales", "ft"],
    ["es_large", "Large", "Grandes", "h"],
    ["es_huge", "Huge", "Enormes", "ft"],
    ["es_hooded", "Hooded", "Encapotados", "h"],
    ["es_upturned", "Upturned", "Hacia arriba", "h"],
    ["es_downturned", "Downturned", "Hacia abajo", "h"],
  ]),
  g("eye_color", "Color de ojos", "Eye color", 1, "eye color", [
    ["eye_black", "Black", "Negros", "h"],
    ["eye_brown", "Brown", "Cafés", "h"],
    ["eye_hazel", "Hazel", "Avellana", "h"],
    ["eye_green", "Green", "Verdes", "h"],
    ["eye_blue", "Blue", "Azules", "h"],
    ["eye_ice_blue", "Ice blue", "Azul hielo", "h"],
    ["eye_amber", "Amber", "Ámbar", "h"],
    ["eye_grey", "Grey", "Grises", "h"],
  ]),
  g("freak_face", "Rasgos", "Features", 4, "facial features", [
    ["fn_freckles", "Freckles", "Pecas", "h"],
    ["fn_dimples", "Dimples", "Hoyuelos", "h"],
    ["fn_eyebags", "Heavy eye bags", "Ojeras marcadas", "h"],
    ["ff_marks_12", "Blush", "Rubor", "ft"],
    ["fn_cheekbones", "High cheekbones", "Pómulos altos", "h"],
    ["fn_fulllips", "Full lips", "Labios gruesos", "h"],
    ["fn_thickbrows", "Thick brows", "Cejas gruesas", "h"],
    ["fn_mole", "Beauty mark", "Lunar", "h"],
    ["ff_nose_0", "Potato nose", "Nariz de papa", "ft"],
    ["ff_nose_1", "Button nose", "Nariz de botón", "ft"],
    ["ff_nose_2", "Pointy nose", "Nariz puntiaguda", "ft"],
    ["fn_tinynose", "Tiny nose", "Nariz diminuta", "h"],
    ["ff_lips_3", "Pouty lips", "Labios carnosos", "ft"],
    ["ff_lips_4", "Tiny pursed mouth", "Boca fruncida", "ft"],
    ["fn_widemouth", "Wide mouth", "Boca ancha", "h"],
    ["ff_brows_5", "Unibrow", "Uniceja", "ft"],
    ["ff_brows_6", "Thin high brows", "Cejas finas y altas", "ft"],
    ["ff_brows_7", "Brush brows", "Cejas de cepillo", "ft"],
    ["ff_ears_8", "Jug ears", "Orejas de soplillo", "ft"],
    ["ff_ears_9", "Uneven ears", "Orejas desiguales", "ft"],
    ["ff_teeth_10", "Gap teeth", "Dientes separados", "ft"],
    ["ff_teeth_11", "Buck teeth", "Dientes de conejo", "ft"],
    ["fn_pointychin", "Pointy chin", "Barbilla puntiaguda", "h"],
    ["ff_chin_13", "Weak chin", "Barbilla hundida", "ft"],
    ["ff_forehead_14", "Big forehead", "Frente grande", "ft"],
  ]),
  g("facial_hair", "Vello facial", "Facial hair", 1, "facial hair", [
    ["fh_none", "Clean", "Afeitado", "a"],
    ["fh_stubble", "Stubble", "Barba de tres días", "a"],
    ["fh_beard", "Full beard", "Barba completa", "a"],
    ["fh_goatee", "Goatee", "Perilla", "a"],
    ["fh_moustache", "Moustache", "Bigote", "a"],
    ["fh_pencil", "Pencil", "Bigote fino", "a"],
    ["fh_pushbroom", "Push-broom", "Bigote de escoba", "fa"],
    ["fh_braid", "Braided", "Barba trenzada", "fa"],
  ]),
  g("distinctive", "Rasgos distintivos", "Distinctive features", 2, "distinctive features", [
    ["df_hetero", "Odd eyes", "Ojos de dos colores", "a"],
    ["df_facetattoo", "Face tattoo", "Tatuaje facial", "a"],
    ["df_septum", "Piercing", "Piercing", "a"],
    ["df_ears", "Ear piercing", "Piercings en las orejas", "a"],
    ["df_slits", "Brow slits", "Cortes en la ceja", "a"],
    ["df_bleached", "Bleached", "Cejas decoloradas", "a"],
    ["df_nobrows", "No brows", "Sin cejas", "a"],
    ["df_grill", "Gold grill", "Grill de oro", "a"],
    ["df_braces", "Braces", "Brackets", "a"],
    ["df_scar", "Brow scar", "Cicatriz en la ceja", "a"],
    ["df_gems", "Face gems", "Gemas en la cara", "a"],
    ["df_elf", "Elf ears", "Orejas de elfo", "a"],
    ["df_lashes", "Big lashes", "Pestañas enormes", "a"],
    ["df_bandage", "Nose tape", "Cinta en la nariz", "a"],
  ]),
  g("accessory", "Accesorios", "Accessories", 3, "accessories", [
    ["acc_none", "None", "Ninguno", "a"],
    ["acc_glasses", "Glasses", "Gafas", "a"],
    ["acc_headphones", "Headphones", "Audífonos", "a"],
    ["acc_jewelry", "Jewelry", "Joyas", "a"],
    ["acc_hat", "Hat", "Sombrero", "a"],
    ["acc_bag", "Bag", "Bolso", "a"],
  ]),
];

export type Selection = Record<string, string[]>;
export type Example = { id: string; thumb: string; w: number; h: number; tier: Tier; sel: Selection; brief: string; seed: number };

const ex = (id: string, thumb: string, w: number, h: number, tier: Tier, sel: Selection, seed: number, brief = ""): Example => ({
  id,
  thumb: CDN + thumb,
  w,
  h,
  tier,
  sel,
  brief,
  seed,
});

/** Los ejemplos de la galería de Higgsfield, en su orden (prioridad). */
export const EXAMPLES: Example[] = [
  ex("9fe66e84", "published/9252b19379108ae708458738df92b8565df0c0b25ae5930f09c2b6752cbd0965", 1744, 2336, "freak",
    { age: ["adult"], hair: ["hair_bowl"], gender: ["male"], height: ["h_tall"], accessory: ["acc_none"], aesthetic: ["goth"], body_type: ["body_ultra"], eye_color: ["eye_brown"], eye_shape: ["es_almond"], skin_tone: ["st_olive"], freak_face: ["fn_thickbrows"], freak_head: ["head_round"], freak_neck: ["neck_column"], facial_hair: ["fh_pushbroom"], hair_colour: ["hc_black"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["middle_eastern"] },
    427752, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary goth/streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head and hair in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Signature: thick glossy black mushroom bowl cut, heavy black horseshoe moustache, metal braces on the teeth, hyper-muscular body. Outfit: black leather vest over a black shirt with rolled sleeves, wide black leather belt, emerald-green velvet flared trousers, black leather gloves, black heeled boots. Hyper-realistic, natural uniform skin tone, crisp texture, sharp focus."),
  ex("ea7885fc", "published/1f47e7fff8f467c11975a089935c002c03c80084cce7db04e52e23fa4ef2e6a4", 1024, 1024, "freak",
    { age: ["adult"], hair: ["hs_lampshade"], gender: ["male"], height: ["h_tall"], aesthetic: ["sporty"], body_type: ["body_athletic"], eye_color: ["eye_blue"], eye_shape: ["es_almond"], skin_tone: ["st_porcelain"], freak_face: ["fn_dimples"], freak_head: ["head_oval"], freak_neck: ["neck_normal"], distinctive: ["df_scar"], facial_hair: ["fh_moustache"], hair_colour: ["hc_chestnut"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["european"] },
    329596),
  ex("f1754b73", "published/ef446f6f5e626085f77c31306db50f11f09ca77b59ad9c749f7e1667822a61c5", 1360, 2048, "freak",
    { age: ["adult"], hair: ["hs_dome"], gender: ["female"], height: ["h_very_tall"], accessory: ["acc_none"], aesthetic: ["streetstyle"], body_type: ["body_slim"], eye_color: ["eye_brown"], eye_shape: ["es_almond"], skin_tone: ["st_ebony"], freak_face: ["fn_cheekbones"], freak_head: ["head_long"], freak_neck: ["neck_long"], facial_hair: ["fh_none"], hair_colour: ["hc_platinum"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["african"] },
    918241, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary trendy 2026 runway styling (not retro). Two-panel sheet: left a tight close-up portrait with the entire head and hair in frame, right a full-body standing shot; both front-facing, arms down, blank expression. PURE WHITE seamless background, bright soft light. Slim, not overweight. Signature: extremely long thin neck, tall bleached-blonde flat-top haircut like a box. Outfit: lime-green fuzzy mohair cropped cardigan, brown leather midi skirt, white knee socks, chunky black loafers. Hyper-realistic, natural uniform skin tone, crisp texture, 85mm, sharp focus."),
  ex("b6ecfaa9", "published/33e71d15f64fd4af32e9d128bef2b724af4f599f6004d5fc2171afc50d500dd1", 1024, 1024, "freak",
    { hair: ["hair_mullet"], gender: ["male"], aesthetic: ["sporty"], body_type: ["body_athletic"], hair_colour: ["hc_black"] }, 375122),
  ex("94e7114c", "a50801ab9f8c7466f30c9d1da6b7f1a6c3070143f1fd1b1ce17d07d4079f7266.webp", 1024, 688, "total",
    { age: ["senior"], hair: ["hs_tufts"], gender: ["trans_woman"], height: ["h_very_tall"], accessory: ["acc_glasses"], aesthetic: ["casual"], body_type: ["body_muscular"], eye_color: ["eye_brown"], eye_shape: ["es_monolid"], skin_tone: ["st_deep"], freak_face: ["ff_teeth_10"], freak_head: ["head_square"], freak_neck: ["neck_long"], distinctive: ["df_scar"], facial_hair: ["fh_none"], hair_colour: ["hc_grey"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["latin_american"] },
    345024),
  ex("2b943a92", "published/f2f9ba4da235c11d8a0ea960cd5ab34de312c7143fae3cd9a88e6b5e9483faa1", 1792, 2240, "freak",
    { age: ["adult"], hair: ["hair_bowl"], gender: ["male"], height: ["h_tall"], accessory: ["acc_none"], aesthetic: ["casual"], body_type: ["body_ultra"], eye_color: ["eye_brown"], eye_shape: ["es_almond"], skin_tone: ["st_deep"], freak_face: ["fn_cheekbones"], freak_head: ["head_tiny"], freak_neck: ["neck_column"], facial_hair: ["fh_none"], hair_colour: ["hc_platinum"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["african"] },
    330951, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary trendy 2026 runway styling (not retro). Two-panel sheet: left a tight close-up portrait with the entire head and hair in frame, right a full-body standing shot; both front-facing, arms down, blank expression. PURE WHITE seamless background, bright soft light. Not overweight. Signature: hyper-muscular bodybuilder physique with a very small head, platinum bowl cut, deadpan face. Outfit: tight cropped baby-blue knit polo stretched over huge muscles, baggy brown corduroy carpenter pants, clogs with white socks. Hyper-realistic, natural uniform skin tone, crisp texture, 85mm, sharp focus."),
  ex("4d1a3816", "published/f0074246264cff6c267542faa56deba27d1e63742d749a2f1063ccd52677641e", 1360, 2048, "freak",
    { age: ["senior"], hair: ["hair_long"], gender: ["male"], height: ["h_very_tall"], accessory: ["acc_glasses", "acc_jewelry"], aesthetic: ["goth"], body_type: ["body_slim"], eye_color: ["eye_grey"], eye_shape: ["es_hooded"], skin_tone: ["st_fair"], freak_face: ["fn_eyebags"], freak_head: ["head_long"], freak_neck: ["neck_long"], facial_hair: ["fh_braid"], hair_colour: ["hc_white"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["european"] },
    477836, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary biker/streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head and hair in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Slim, not overweight. Signature: very long straight white hair with a center part, long braided white goatee, black wraparound sunglasses, deeply wrinkled gaunt face. Outfit: black leather biker jacket, plain black tee, black flared jeans, black cowboy boots, chunky silver chains and rings. Hyper-realistic, natural uniform skin tone, crisp texture, sharp focus."),
  ex("0805b749", "published/69806e5c2c4d407e70a08a9862522e91be7872388f97ce696b1f86b34db86df2", 2240, 1792, "total",
    { age: ["adult"], hair: ["hs_dome"], gender: ["male"], height: ["h_tall"], accessory: ["acc_none"], aesthetic: ["streetstyle"], body_type: ["body_athletic"], eye_color: ["eye_brown"], eye_shape: ["es_hooded"], skin_tone: ["st_olive"], freak_face: ["fn_thickbrows"], freak_head: ["head_ancient"], freak_neck: ["neck_short"], facial_hair: ["fh_stubble"], hair_colour: ["hc_black"], ethnicity_origin_base: ["middle_eastern"] },
    671790, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary workwear/streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head and hair in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Signature: caveman skull with a massive protruding brow ridge, wide flat nose, black curly high-top fade. Outfit: bright orange canvas work jacket over a black hoodie, baggy olive cargo pants, tan construction boots, chain wallet. Hyper-realistic, natural uniform skin tone, crisp texture, sharp focus."),
  ex("d112cf02", "74d0701fef4fbbab6de02e3047939632679c67089929b3343d533f99ba2b6c8a.webp", 896, 1120, "total",
    { age: ["mature"], hair: ["hs_lampshade"], gender: ["trans_man"], height: ["h_average"], accessory: ["acc_jewelry"], aesthetic: ["retro"], body_type: ["body_heavy"], eye_color: ["eye_ice_blue"], eye_shape: ["es_close"], skin_tone: ["st_porcelain"], freak_face: ["ff_ears_9"], freak_head: ["head_ancient"], freak_neck: ["neck_normal"], distinctive: ["df_ears"], facial_hair: ["fh_pencil"], hair_colour: ["hc_lilac"], proportions: ["pr_shortlegs"], ethnicity_origin_base: ["african"] },
    476164),
  ex("7ab45ed9", "published/91c23e5c7b1a5b01054c9eaeb00700fd853e0850d413897ba907dc59ccc3e058", 1520, 2688, "freak",
    { age: ["adult"], hair: ["hair_long"], gender: ["female"], height: ["h_tall"], accessory: ["acc_jewelry"], aesthetic: ["streetstyle"], body_type: ["body_ultra"], eye_color: ["eye_brown"], eye_shape: ["es_almond"], skin_tone: ["st_deep"], freak_face: ["ff_brows_6"], freak_head: ["head_oval"], freak_neck: ["neck_column"], facial_hair: ["fh_none"], hair_colour: ["hc_black"], proportions: ["pr_shoulders", "pr_waist"], ethnicity_origin_base: ["african"] },
    905384, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head and hair in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Not overweight. Signature: hyper-muscular woman, tight cornrows pulled into a high bun, bold drawn-on brows, gold grill teeth. Outfit: cropped black leather jacket, black mesh top, baggy camo cargo pants, chunky white sneakers. Hyper-realistic, natural uniform skin tone, crisp texture, sharp focus."),
  ex("552eb0bc", "71141a86f8c3d205f549a42c9324464b6b1ccf242644137d22913e5276e11101.webp", 1344, 752, "total",
    { age: ["senior"], hair: ["hs_dome"], gender: ["trans_man"], height: ["h_average"], accessory: ["acc_hat"], aesthetic: ["retro"], body_type: ["body_athletic"], eye_color: ["eye_ice_blue"], eye_shape: ["es_upturned"], skin_tone: ["st_tan"], freak_face: ["ff_lips_3"], freak_head: ["head_forehead"], freak_neck: ["neck_long"], distinctive: ["df_septum"], facial_hair: ["fh_pushbroom"], hair_colour: ["hc_pink"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["african"] },
    651151),
  ex("8b492a5f", "5d7a2e41f276626b1ce58dbf58f2d539e7d94c6e4343d7cdaf3fb466cebcc4ee.webp", 752, 1344, "total",
    { age: ["senior"], hair: ["hs_dome"], gender: ["male"], height: ["h_average"], accessory: ["acc_none"], aesthetic: ["sporty"], body_type: ["body_muscular"], skin_tone: ["st_fair"], freak_face: ["ff_teeth_10", "fn_freckles"], freak_head: ["head_herojaw"], facial_hair: ["fh_pushbroom"], hair_colour: ["hc_ginger"], proportions: ["pr_shortlegs", "pr_shoulders"], ethnicity_origin_base: ["european"] },
    522857, "Retired 80s aerobics instructor: senior man with a huge chiseled gigachad jaw, enormous tight ginger perm like a giant ball, bushy ginger push-broom moustache, neon pink terry headband, gap teeth grin. Shiny teal-and-purple windbreaker tracksuit, white tube socks pulled high, chunky white retro sneakers, sweat wristbands, tiny skinny legs under a broad barrel chest. Hyperreal practical-prosthetic character, deadpan expression, standing straight, pure white seamless studio backdrop, high-end fashion lookbook photo, extremely exaggerated but photoreal."),
  ex("8dc7c2e4", "published/ee39904f2135e90b70746f3288de99d0a4c9c24662561cf4f6253c532d94c4d0", 1360, 2048, "freak",
    { age: ["adult"], hair: ["hs_pompadour"], gender: ["female"], height: ["h_tall"], accessory: ["acc_jewelry"], aesthetic: ["streetstyle"], body_type: ["body_slim"], eye_color: ["eye_blue"], eye_shape: ["es_almond"], skin_tone: ["st_porcelain"], freak_face: ["ff_lips_3"], freak_head: ["head_oval"], freak_neck: ["neck_long"], facial_hair: ["fh_none"], hair_colour: ["hc_platinum"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["european"] },
    62265, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary club/streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head and hair in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Slim, not overweight. Signature: bleached eyebrows, platinum wet-look hair slicked straight back, huge pouty lips, multiple silver facial piercings on brow and lip. Outfit: black latex top, oversized grey pinstripe blazer, baggy dark jeans, pointed silver metallic boots. Hyper-realistic, natural uniform skin tone, crisp texture, sharp focus."),
  ex("a617c588", "published/65be9b10832e4cfa8b07cec657cfc2ee4d100cb8ab7f5f55ec7a6176ffd43fff", 2336, 1744, "freak",
    { age: ["adult"], hair: ["hair_buzz"], gender: ["male"], height: ["h_tall"], accessory: ["acc_jewelry"], aesthetic: ["y2k"], body_type: ["body_slim"], eye_color: ["eye_grey"], eye_shape: ["es_close"], skin_tone: ["st_fair"], freak_face: ["ff_nose_2", "ff_ears_8"], freak_head: ["head_oval"], freak_neck: ["neck_long"], distinctive: ["df_ears"], facial_hair: ["fh_none"], hair_colour: ["hc_platinum"], ethnicity_origin_base: ["european"] },
    318842, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary y2k streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Slim, not overweight. Signature: shaved head with a tiny bleached micro-fringe, huge hooked nose, prominent ears, metal braces. Outfit: purple satin bomber jacket, white ribbed tank, grey sweatpants, black slides with white socks, silver chains. Hyper-realistic, natural uniform skin tone, crisp texture, sharp focus."),
  ex("9aeccf46", "706d30a34e1a0a3f2bd8b8bb74b0f84925de3b986cfdd2531324114845f585c1.webp", 1024, 1024, "total",
    { age: ["adult"], hair: ["hs_horns"], gender: ["trans_woman"], height: ["h_very_tall"], accessory: ["acc_glasses"], aesthetic: ["retro"], body_type: ["body_athletic"], eye_color: ["eye_black"], eye_shape: ["es_uneven"], skin_tone: ["st_deep"], freak_face: ["fn_freckles"], freak_head: ["head_tiny"], freak_neck: ["neck_short"], distinctive: ["df_bleached"], facial_hair: ["fh_none"], hair_colour: ["hc_white"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["east_asian"] },
    879855),
  ex("15ae2b44", "263e937568b3798baa500c358cd9eabc52e6f5e9e70fc928951fd8374cf9a37f.webp", 1024, 1024, "normal",
    { age: ["mature"], hair: ["hair_pigtails"], gender: ["female"], height: ["h_average"], accessory: ["acc_hat"], aesthetic: ["retro"], body_type: ["body_heavy"], eye_color: ["eye_hazel"], eye_shape: ["es_downturned"], skin_tone: ["st_deep"], freak_face: ["fn_freckles"], freak_head: ["head_oval"], freak_neck: ["neck_short"], distinctive: ["df_hetero"], facial_hair: ["fh_none"], hair_colour: ["hc_white"], proportions: ["pr_shortlegs"], ethnicity_origin_base: ["african"] },
    860447),
  ex("778bc86d", "03db86ea9915c829fbfdeda4a98d0e5ee45e2035c86f276cbfac256e66da0974.webp", 1024, 688, "total",
    { age: ["senior"], hair: ["hs_beehive"], gender: ["female"], height: ["h_average"], accessory: ["acc_jewelry"], aesthetic: ["theatrical"], body_type: ["body_slim"], skin_tone: ["st_brown"], freak_face: ["fn_mole", "ff_brows_6"], freak_head: ["head_heart"], distinctive: ["df_hetero", "df_lashes"], hair_colour: ["hc_white"], ethnicity_origin_base: ["indian"] },
    167765, "Stern elderly salon owner with an enormous towering white beehive twice the height of her head, thin arched high brows, one blue and one brown eye, long false lashes, beauty mark. Fitted purple hairdresser tunic with combs and scissors in the chest pocket, holding silver scissors in one hand and a round brush in the other, black cigarette trousers, plum horsebit loafers. Hyperreal practical-prosthetic character, deadpan expression, standing straight, pure white seamless studio backdrop, high-end fashion lookbook photo, extremely exaggerated but photoreal."),
  ex("9d62f679", "3d4457f8236330f37ec7681271e20ed969b0de844d8c00079b1b4f3b6a125681.webp", 752, 1344, "total",
    { age: ["adult"], hair: ["hs_beehive"], gender: ["female"], height: ["h_very_tall"], accessory: ["acc_headphones"], aesthetic: ["goth"], body_type: ["body_curvy"], eye_color: ["eye_hazel"], eye_shape: ["es_hooded"], skin_tone: ["st_tan"], freak_face: ["fn_eyebags"], freak_head: ["head_forehead"], freak_neck: ["neck_normal"], distinctive: ["df_hetero"], facial_hair: ["fh_none"], hair_colour: ["hc_pink"], proportions: ["pr_waist"], ethnicity_origin_base: ["east_asian"] },
    671172),
  ex("c6c24c39", "7ec145349c9101ec6e72176a925950ace13fc655286c5a443fbc558da57494eb.webp", 1344, 752, "total",
    { age: ["senior"], hair: ["hs_wings"], gender: ["trans_man"], height: ["h_very_tall"], accessory: ["acc_hat"], aesthetic: ["retro"], body_type: ["body_muscular"], eye_color: ["eye_amber"], eye_shape: ["es_upturned"], skin_tone: ["st_deep"], freak_face: ["ff_teeth_10"], freak_head: ["head_long"], freak_neck: ["neck_column"], distinctive: ["df_lashes"], facial_hair: ["fh_stubble"], hair_colour: ["hc_green"], proportions: ["pr_waist"], ethnicity_origin_base: ["african"] },
    656681),
  ex("ca20a74c", "9b7ed7c557abc66ff7f64a6b86778c0946792255ca27eef9dffb8f47ea25246f.webp", 752, 1344, "freak",
    { age: ["adult"], hair: ["hair_pigtails"], gender: ["male"], height: ["h_very_tall"], accessory: ["acc_jewelry"], aesthetic: ["retro"], body_type: ["body_slim"], eye_color: ["eye_black"], eye_shape: ["es_upturned"], skin_tone: ["st_olive"], freak_face: ["ff_brows_5"], freak_head: ["head_heart"], freak_neck: ["neck_column"], distinctive: ["df_ears"], facial_hair: ["fh_pencil"], hair_colour: ["hc_black"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["east_asian"] },
    695297),
  ex("36e03d67", "67f2c7c1d6e0ec78464cdb21474748288a23fa827aafe9587c775bc222c39f67.webp", 752, 1344, "total",
    { age: ["senior"], hair: ["hs_pompadour"], gender: ["female"], height: ["h_average"], accessory: ["acc_none"], aesthetic: ["y2k"], body_type: ["body_heavy"], eye_color: ["eye_blue"], eye_shape: ["es_large"], skin_tone: ["st_light"], freak_face: ["ff_brows_7"], freak_head: ["head_herojaw"], freak_neck: ["neck_short"], distinctive: ["df_lashes"], facial_hair: ["fh_moustache"], hair_colour: ["hc_grey"], proportions: ["pr_shortlegs"], ethnicity_origin_base: ["middle_eastern"] },
    613263),
  ex("9dc6f315", "published/fdf3ab3b44cff468d24910995ad43f6ab877836d3bf16216bdfc20f630bd563f", 1664, 2496, "freak",
    { age: ["senior"], hair: ["hs_tufts"], gender: ["male"], height: ["h_tall"], accessory: ["acc_glasses"], aesthetic: ["retro"], body_type: ["body_slim"], eye_color: ["eye_grey"], eye_shape: ["es_hooded"], skin_tone: ["st_fair"], freak_face: ["ff_nose_2", "fn_eyebags"], freak_head: ["head_long"], freak_neck: ["neck_long"], facial_hair: ["fh_moustache"], hair_colour: ["hc_white"], ethnicity_origin_base: ["european"] },
    937695, "Classic eccentric 'freak' character, deadpan art-house casting photo; a believable real odd-looking person, understated, not a cartoon. Two-panel character sheet: left half a tight head-and-shoulders portrait, right half a full-body standing shot, both front-facing, symmetrical, arms hanging straight down, blank deadpan expression. PURE WHITE seamless studio background (#FFFFFF) in both panels, no grey, no gradient, no vignette, soft even light, faint contact shadow under the feet. Slim build, not overweight. Hair: bald crown with fluffy white tufts above the ears. Thin white moustache, small round wire glasses. Outfit: grey flannel three-piece suit, navy bow tie, black oxford shoes. No tattoos, no piercings. Hyper-realistic editorial photography, visible skin texture and fabric weave, 85mm lens, sharp focus."),
  ex("4bec30e5", "published/a3b8a77c35e73ab0b82c37209552ba97d63ce5d8fa3f48f7e97d90543fad77ae", 1536, 2720, "total",
    { age: ["adult"], hair: ["hair_mullet"], gender: ["male"], height: ["h_very_tall"], accessory: ["acc_none"], aesthetic: ["streetstyle"], body_type: ["body_slim"], eye_color: ["eye_brown"], eye_shape: ["es_almond"], skin_tone: ["st_deep"], freak_face: ["fn_cheekbones"], freak_head: ["head_megachin"], freak_neck: ["neck_long"], distinctive: ["df_septum"], facial_hair: ["fh_pencil"], hair_colour: ["hc_darkbrown"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["african"] },
    104904, "EXTREME hypertrophied 'freak' character, surreal but photoreal fashion-editorial casting photo, the signature feature is wildly exaggerated. Two-panel character sheet: left half an extreme tight close-up portrait filling the frame, right half a full-body standing shot, both front-facing, symmetrical, arms down, blank serious expression. PURE WHITE seamless background (#FFFFFF), bright high-key soft light, soft floor shadow. Slim, not overweight. Signature: a gigantic mega jaw, lower face swollen twice as wide as the forehead, very long thick neck. Curly dark brown mullet, thin moustache, silver septum ring. Outfit: chrome-silver cropped puffer jacket, black ribbed tank, wide black cargo trousers, chunky black boots. Hyper-realistic high-end fashion photography, crisp skin texture, sharp focus."),
  ex("ac6d3d09", "published/e96e29e56c66490f124a439c0774b408e32b399a02da2fc3983427aad82bfd2b", 1760, 2352, "total",
    { age: ["mature"], hair: ["hair_long"], gender: ["male"], height: ["h_tall"], accessory: ["acc_none"], aesthetic: ["retro"], body_type: ["body_slim"], eye_color: ["eye_brown"], eye_shape: ["es_hooded"], skin_tone: ["st_olive"], freak_face: ["ff_brows_5"], freak_head: ["head_ancient"], freak_neck: ["neck_normal"], facial_hair: ["fh_stubble"], hair_colour: ["hc_black"], ethnicity_origin_base: ["middle_eastern"] },
    557550, "EXTREME hypertrophied 'freak' character, surreal but photoreal fashion-editorial casting photo, the signature feature is wildly exaggerated. Two-panel character sheet: left half an extreme tight close-up portrait filling the frame, right half a full-body standing shot, both front-facing, symmetrical, arms down, blank serious expression. PURE WHITE seamless background (#FFFFFF), bright high-key soft light, soft floor shadow. Slim, not overweight. Signature: caveman skull with a massive protruding brow ridge and one thick unibrow, deep-set eyes, heavy jaw. Contrast: sleek long jet-black hair with a perfect center part. Outfit: immaculate slim light-grey suit, white shirt, thin black tie, black loafers. Hyper-realistic high-end fashion photography, crisp skin texture, sharp focus."),
  ex("5f0238e6", "published/9f5cb3e7b856185cd3ec9aa59959ec011c88c3efc87dfa61606b719dbf27e7a1", 1536, 2720, "total",
    { age: ["senior"], hair: ["hair_bald"], gender: ["male"], height: ["h_tall"], accessory: ["acc_none"], aesthetic: ["retro"], body_type: ["body_slim"], eye_color: ["eye_grey"], eye_shape: ["es_hooded"], skin_tone: ["st_fair"], freak_face: ["fn_eyebags"], freak_head: ["head_round"], freak_neck: ["neck_normal"], facial_hair: ["fh_moustache"], hair_colour: ["hc_white"], ethnicity_origin_base: ["european"] },
    668535, "EXTREME hypertrophied 'freak' character, surreal but photoreal fashion-editorial casting photo, the signature feature is wildly exaggerated. Two-panel character sheet: left half an extreme tight close-up portrait filling the frame, right half a full-body standing shot, both front-facing, symmetrical, arms down, blank serious expression. PURE WHITE seamless background (#FFFFFF), bright high-key soft light, soft floor shadow. Slim, not overweight. Signature: colossal waxed white handlebar moustache spanning wider than his shoulders, both ends curled into perfect tight spirals. Shiny bald head. Outfit: bottle-green velvet three-piece suit, cream shirt, gold pocket-watch chain, brown boots. Hyper-realistic high-end fashion photography, crisp skin texture, sharp focus."),
  ex("b28a9d78", "published/704a8a4d3432ce2282780f449d9a7f7336c321ac5ec23bfa631d3417faba0a9b", 2496, 1664, "total",
    { age: ["adult"], hair: ["hs_lampshade"], gender: ["male"], height: ["h_tall"], accessory: ["acc_glasses"], aesthetic: ["retro"], body_type: ["body_slim"], eye_color: ["eye_ice_blue"], eye_shape: ["es_close"], skin_tone: ["st_light"], freak_face: ["ff_brows_6"], freak_head: ["head_megachin"], freak_neck: ["neck_column"], distinctive: ["df_ears"], facial_hair: ["fh_none"], hair_colour: ["hc_platinum"], proportions: ["pr_waist"], ethnicity_origin_base: ["european"] },
    383987, "Extreme exaggerated anatomy, surreal but photoreal fashion portrait. Man with a gigantic mega jaw twice as wide as his skull and a thick column neck. Platinum lampshade bob with a blunt fringe, thin high eyebrows, small black oval sunglasses. Fully dressed: burgundy knit polo shirt buttoned up, cream pleated wide trousers, oxblood loafers. Deadpan expression. Pure white background."),
  ex("5d0d20e3", "published/537d9815f150f6b610320e835392d36e8fd67401d9ef926a5f2b49e9473a09e4", 2048, 2048, "total",
    { age: ["adult"], hair: ["hs_sphere"], gender: ["non_binary"], height: ["h_very_tall"], accessory: ["acc_none"], aesthetic: ["goth"], body_type: ["body_slim"], eye_color: ["eye_black"], eye_shape: ["es_downturned"], skin_tone: ["st_porcelain"], freak_face: ["fn_fulllips"], freak_head: ["head_tiny"], freak_neck: ["neck_long"], distinctive: ["df_nobrows"], facial_hair: ["fh_none"], hair_colour: ["hc_platinum"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["european"] },
    485806, "Extreme exaggerated anatomy, surreal but photoreal. Very tall androgynous person with a comically tiny head on a long lanky body with extremely long limbs. Platinum curl sphere hair, no eyebrows. Oxblood leather long coat, black crushed velvet top, black leather trousers, black lace-up combat boots. Deadpan expression. Pure white background."),
  ex("b42d827e", "published/d5a327953d1c899e3a3717199249dca0bc7908b5e17427e8edd1194c860d9bd1", 1760, 2352, "total",
    { age: ["mature"], hair: ["hair_mullet"], gender: ["male"], height: ["h_very_tall"], accessory: ["acc_glasses"], aesthetic: ["retro"], body_type: ["body_heavy"], eye_color: ["eye_blue"], eye_shape: ["es_large"], skin_tone: ["st_tan"], freak_face: ["fn_widemouth"], freak_head: ["head_herojaw"], freak_neck: ["neck_short"], distinctive: ["df_grill"], facial_hair: ["fh_pushbroom"], hair_colour: ["hc_grey"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["latin_american"] },
    652478, "Extreme exaggerated anatomy, surreal but photoreal. Heavy man with an enormous square gigachad jaw. Grey mullet, huge grey push-broom moustache, amber-tinted aviator glasses. Tan suede western jacket with fringe, brown shirt, bolo tie, brown flared trousers, cowboy boots. Deadpan expression. Pure white background."),
  ex("4a9e6a43", "published/3996b04bae549f6aabc3aed42f194c55d79a8747f9379073897c9f8f8d5d9d51", 2048, 1360, "total",
    { age: ["mature"], hair: ["hs_wings"], gender: ["male"], height: ["h_very_tall"], accessory: ["acc_none"], aesthetic: ["theatrical"], body_type: ["body_slim"], eye_color: ["eye_brown"], eye_shape: ["es_hooded"], skin_tone: ["st_tan"], freak_face: ["ff_nose_2"], freak_head: ["head_long"], freak_neck: ["neck_long"], facial_hair: ["fh_pencil"], hair_colour: ["hc_black"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["latin_american"] },
    393901, "EXTREME hypertrophied 'freak' character, surreal but photoreal fashion-editorial casting photo, the signature feature is wildly exaggerated. Two-panel character sheet: left half an extreme tight close-up portrait filling the frame, right half a full-body standing shot, both front-facing, symmetrical, arms down, blank serious expression. PURE WHITE seamless background (#FFFFFF), bright high-key soft light, soft floor shadow. Slim, not overweight. Signature: jet-black hair lacquered into one giant crescent-moon shape arching high over the head from ear to ear like a halo. Long pointy nose, pencil moustache. Outfit: black velvet tuxedo jacket, white ruffled shirt, black bow tie, black trousers, patent shoes. Hyper-realistic high-end fashion photography, crisp skin texture, sharp focus."),
  ex("536d5d37", "published/416e140c19172071ac930a8f7998b4aed3b95dfd8543eb4454478ad8d43e68b5", 1360, 2048, "freak",
    { age: ["senior"], hair: ["hs_pompadour"], gender: ["male"], accessory: ["acc_none"], aesthetic: ["retro"], body_type: ["body_heavy"], facial_hair: ["fh_none"], hair_colour: ["hc_ginger"] },
    921780, "A two-panel photorealistic character sheet: LEFT panel, deadpan chest-up studio portrait; RIGHT panel, the exact same person full body, standing straight, arms at sides, head to toe. Both panels on a light grey seamless studio background, flat even lighting, fine film grain, identical person and outfit in both panels. THE CHARACTER: a short, round man around 60 with an impossibly TALL copper POMPADOUR rising thirty centimeters straight up like a loaf of bread, perfectly groomed; clear skin, double chin, completely serious stare; powder-blue 1970s suit with wide lapels, white shirt, oversized tie knot, white loafers. No text, no logos, no watermarks."),
  ex("3a5f4720", "published/0b5c4d6e992c3d42b838f1a95bd73305aa10cc7151d533ddcec79a56d7894497", 2688, 1520, "freak",
    { age: ["adult"], gender: ["male"], accessory: ["acc_none"], aesthetic: ["suits"], body_type: ["body_slim"], facial_hair: ["fh_pencil"] },
    534225, "A two-panel photorealistic character sheet: LEFT panel, deadpan chest-up studio portrait; RIGHT panel, the exact same person full body, standing straight, arms at sides, head to toe. Both panels on a light grey seamless studio background, flat even lighting, fine film grain, identical person and outfit in both panels. THE CHARACTER: an eccentric dandy around 35 whose short flat-top haircut is dyed in a precise CHECKERBOARD pattern, alternating black and bleached-white squares across the whole scalp; clear even skin, pencil moustache, haughty blank expression; black-and-white houndstooth suit, white shirt, black bow tie, two-tone spectator shoes. No text, no logos, no watermarks."),
  ex("9345a815", "published/605def0a25ecbbd1fde3a02c2f776ebd23301ca538192c39512d54c38dac7c2b", 2048, 2048, "freak",
    { age: ["adult"], hair: ["hair_bowl"], gender: ["male"], height: ["h_very_tall"], accessory: ["acc_none"], aesthetic: ["retro"], body_type: ["body_slim"], eye_color: ["eye_blue"], eye_shape: ["es_close"], skin_tone: ["st_fair"], freak_face: ["ff_chin_13", "ff_nose_2"], freak_head: ["head_long"], freak_neck: ["neck_long"], facial_hair: ["fh_none"], hair_colour: ["hc_blonde"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["european"] },
    685325, "Classic eccentric 'freak' character, deadpan art-house casting photo; a believable real odd-looking person, understated, not a cartoon. Two-panel character sheet: left half a tight head-and-shoulders portrait, right half a full-body standing shot, both front-facing, symmetrical, arms hanging straight down, blank deadpan expression. PURE WHITE seamless studio background (#FFFFFF) in both panels, no grey, no gradient, no vignette, soft even light, faint contact shadow under the feet. Lanky slim build, not overweight. Hair: straw-blond bowl cut with straight fringe. Weak chin, long pointy nose. Outfit: brown knitted cardigan over a small-check shirt buttoned to the top, too-short beige trousers, white socks, brown lace-up shoes. No tattoos, no piercings. Hyper-realistic editorial photography, visible skin texture and fabric weave, 85mm lens, sharp focus."),
  ex("8f4f9241", "published/3dd81c0d5514bd087748bcc40d422cfde9ff6ccff273cea9d810412f7a2fe2e9", 1360, 2048, "freak",
    { age: ["mature"], hair: ["hair_bowl"], gender: ["male"], height: ["h_tall"], accessory: ["acc_none"], aesthetic: ["retro"], body_type: ["body_athletic"], eye_color: ["eye_brown"], eye_shape: ["es_hooded"], skin_tone: ["st_olive"], freak_face: ["ff_brows_5"], freak_head: ["head_square"], freak_neck: ["neck_normal"], facial_hair: ["fh_pushbroom"], hair_colour: ["hc_black"], ethnicity_origin_base: ["middle_eastern"] },
    491345, "Classic eccentric 'freak' character, deadpan art-house casting photo; a believable real odd-looking person, understated, not a cartoon. Two-panel character sheet: left half a tight head-and-shoulders portrait, right half a full-body standing shot, both front-facing, symmetrical, arms hanging straight down, blank deadpan expression. PURE WHITE seamless studio background (#FFFFFF) in both panels, no grey, no gradient, no vignette, soft even light, faint contact shadow under the feet. Lean athletic build, not overweight. Hair: thick black bowl cut with heavy fringe. Push-broom moustache, unibrow. Outfit: navy double-breasted blazer with gold buttons, white trousers, brown loafers. No tattoos, no piercings. Hyper-realistic editorial photography, visible skin texture and fabric weave, 85mm lens, sharp focus."),
  ex("ff979de7", "published/cf719f5c5602a59c7f48fd459a950c97b28ff6a732d2ae2922e5190186929bde", 2048, 2048, "freak",
    { age: ["adult"], hair: ["hs_horns"], gender: ["female"], height: ["h_tall"], accessory: ["acc_none"], aesthetic: ["y2k"], body_type: ["body_slim"], eye_color: ["eye_brown"], eye_shape: ["es_almond"], skin_tone: ["st_olive"], freak_face: ["ff_brows_5"], freak_head: ["head_oval"], freak_neck: ["neck_long"], facial_hair: ["fh_none"], hair_colour: ["hc_black"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["middle_eastern"] },
    861702, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary trendy 2026 runway styling (not retro). Two-panel sheet: left a tight close-up portrait with the entire head and hair in frame, right a full-body standing shot; both front-facing, arms down, blank expression. PURE WHITE seamless background, bright soft light. Slim, not overweight. Signature: thick black unibrow, black hair coiled into two huge ram-horn buns on the sides of the head. Outfit: cropped silver metallic puffer jacket, long black ribbed knit maxi dress, chunky silver sneakers. Hyper-realistic, natural uniform skin tone, crisp texture, 85mm, sharp focus."),
  ex("8331fd61", "published/7c8df2683f52d68917df2132146cbff4573d5bd1debacc86ed3c636a7decd075", 1360, 2048, "freak",
    { age: ["adult"], hair: ["hs_lampshade"], gender: ["female"], height: ["h_tall"], accessory: ["acc_jewelry"], aesthetic: ["y2k"], body_type: ["body_slim"], eye_color: ["eye_brown"], eye_shape: ["es_almond"], skin_tone: ["st_brown"], freak_face: ["ff_brows_6"], freak_head: ["head_oval"], freak_neck: ["neck_long"], facial_hair: ["fh_none"], hair_colour: ["hc_platinum"], proportions: ["pr_longlimbs"], ethnicity_origin_base: ["african"] },
    674121, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary y2k streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head and hair in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Slim, not overweight. Signature: silver-blonde finger-wave bob glued to the head, thin drawn-on arched brows, huge gold hoop earrings, nose chain to the ear, very long neck. Outfit: red leather racing jacket, white baby tee, low-rise baggy jeans with a wallet chain, white platform sneakers. Hyper-realistic, natural uniform skin tone, crisp texture, sharp focus."),
  ex("ea178c56", "published/cd209e15ba80955a7e333b35a696733b6815c9e9d35ce37cac7203106331cc86", 2048, 2048, "total",
    { age: ["adult"], hair: ["hs_pompadour"], gender: ["male"], height: ["h_tall"], accessory: ["acc_glasses"], aesthetic: ["sporty"], body_type: ["body_athletic"], eye_color: ["eye_blue"], eye_shape: ["es_hooded"], skin_tone: ["st_light"], freak_face: ["fn_cheekbones"], freak_head: ["head_herojaw"], freak_neck: ["neck_column"], facial_hair: ["fh_stubble"], hair_colour: ["hc_platinum"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["european"] },
    886825, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary motocross/streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head and hair in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Signature: cartoonish hero jaw with deep cleft chin, platinum spiky hair, white tape strip across the nose, wraparound sport sunglasses, muscular build. Outfit: navy-and-white motocross jersey, black leather moto trousers, chunky black moto boots, fingerless gloves. Hyper-realistic, natural uniform skin tone across face and jaw, crisp texture, sharp focus."),
  ex("48e07401", "published/2639320339aecf738acc81e25a6792f92ceb00c7f104980b2a127b09bf2268d2", 1360, 2048, "total",
    { age: ["adult"], hair: ["hair_mullet"], gender: ["male"], height: ["h_tall"], accessory: ["acc_glasses", "acc_jewelry"], aesthetic: ["sporty"], body_type: ["body_slim"], eye_color: ["eye_blue"], eye_shape: ["es_hooded"], skin_tone: ["st_fair"], freak_face: ["ff_brows_6"], freak_head: ["head_megachin"], freak_neck: ["neck_column"], facial_hair: ["fh_none"], hair_colour: ["hc_platinum"], ethnicity_origin_base: ["european"] },
    983468, "Fashion-editorial freak casting photo of an odd-looking but photoreal person, contemporary moto/streetwear styling. Two-panel sheet: left a tight frontal close-up portrait with the entire head and hair in frame, right a full-body standing shot; arms down, blank deadpan expression. PURE WHITE seamless background, bright soft light. Signature: very wide heavy jaw, bleached blonde mullet, thin drawn-on brows, gold grill teeth, sport sunglasses pushed up on the head. Outfit: oversized red-and-white leather racing jacket, black tank, baggy blue jeans, black motorcycle boots. Hyper-realistic, natural uniform skin tone across face and jaw, crisp texture, sharp focus."),
  ex("f53eef28", "published/edfa7b7a2f9b94e53fa8cbe32de1c31d2c13bd7013d4a8faa066a041282a008d", 688, 1024, "total",
    { age: ["senior"], hair: ["hs_lampshade"], gender: ["male"], height: ["h_very_tall"], accessory: ["acc_jewelry"], aesthetic: ["theatrical"], body_type: ["body_muscular"], eye_color: ["eye_hazel"], eye_shape: ["es_close"], skin_tone: ["st_tan"], freak_face: ["ff_brows_6"], freak_head: ["head_oval"], freak_neck: ["neck_normal"], distinctive: ["df_gems"], facial_hair: ["fh_pushbroom"], hair_colour: ["hc_chestnut"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["african"] },
    689385),
  ex("3f278510", "published/6ff6a701f477ac2dbae58bd5e6d9a60adf6b373f007ee8a8627de361d9dd7ca5", 688, 1024, "total",
    { age: ["senior"], hair: ["hs_corkscrews"], gender: ["male"], height: ["h_average"], accessory: ["acc_none"], aesthetic: ["y2k"], body_type: ["body_ultra"], eye_color: ["eye_blue"], eye_shape: ["es_monolid"], skin_tone: ["st_porcelain"], freak_face: ["ff_forehead_14", "ff_teeth_10", "ff_nose_2"], freak_head: ["head_long"], freak_neck: ["neck_long"], facial_hair: ["fh_pencil"], hair_colour: ["hc_black"], proportions: ["pr_shoulders"], ethnicity_origin_base: ["east_asian"] },
    428232),
];

const TIER_PROMPT: Record<Tier, string> = {
  normal: "Realistic everyday person, natural believable proportions, fashion-editorial casting photo",
  freak: "Fashion-editorial 'freak' casting photo of an odd-looking but photoreal person, bold distinctive features",
  total: "EXTREME hypertrophied 'freak' character, surreal but photoreal fashion-editorial casting photo, the signature features are wildly exaggerated",
  insects: "Photoreal anthropomorphic character: a realistic insect head with compound eyes and antennae on a human body, practical-prosthetic look",
  frogs: "Photoreal anthropomorphic character: a realistic frog head with glossy skin on a human body, practical-prosthetic look",
  cats: "Photoreal anthropomorphic character: a realistic cat head with fur and whiskers on a human body, practical-prosthetic look",
  dogs: "Photoreal anthropomorphic character: a realistic dog head with fur on a human body, practical-prosthetic look",
  capybaras: "Photoreal anthropomorphic character: a realistic capybara rodent head with fur on a human body, practical-prosthetic look",
  birds: "Photoreal anthropomorphic character: a realistic bird head with feathers and beak on a human body, practical-prosthetic look",
};

const SHEET =
  "Two-panel character sheet: left half a tight frontal close-up portrait with the entire head and hair in frame, right half a full-body standing shot of the exact same person head to toe; both front-facing, arms down, blank deadpan expression. PURE WHITE seamless studio background, bright soft even light, faint floor shadow. Hyper-realistic, natural uniform skin tone, crisp texture, 85mm lens, sharp focus. No text, no logos.";
const SHORT_SHEET = "Two-panel character sheet: close-up portrait left, full body right, pure white background, photoreal.";

/**
 * Prompt en inglés: el brief de un ejemplo (o la base del tipo), los rasgos, la descripción extra del usuario y la
 * hoja de dos paneles. Con `maxLength` (Z-Image admite 800) se acorta la hoja y luego el brief, nunca los rasgos.
 */
/** Texto para el prompt cuando la etiqueta en inglés no basta para describir la opción. */
const OPTION_PROMPT: Record<string, string> = {
  body_hourglass: "fit hourglass figure with a slim toned waist, full bust and round hips, not overweight",
  st_elegant: "elegant formal evening wear",
  st_athlete: "professional athlete in performance sportswear and sneakers",
  st_shorts: "casual above-the-knee shorts",
  st_tank: "sleeveless tank top",
  st_long_skirt: "flowing ankle-length maxi skirt",
  st_mini_skirt: "short mini skirt",
  st_bodycon: "tight fitted bodycon dress",
  st_flowy_dress: "loose flowy dress",
};

export function buildPrompt(
  tier: Tier,
  sel: Selection,
  exampleBrief: string,
  extra: string,
  withPhoto: boolean,
  maxLength?: number,
): string {
  const traits = GROUPS.flatMap((grp) => {
    const labels = (sel[grp.id] ?? [])
      .filter((id) => !["acc_none", "fh_none", "neck_normal", "head_oval"].includes(id))
      .map((id) => OPTION_PROMPT[id] ?? grp.options.find((o) => o.id === id)?.en.toLowerCase())
      .filter(Boolean);
    return labels.length ? [`${grp.prompt}: ${labels.join(", ")}`] : [];
  });
  const head = withPhoto ? "Use the face and identity of the person in the reference photo." : "";
  const traitText = traits.length ? `Traits: ${traits.join("; ")}.` : "";
  const extraText = extra.trim() ? `Details: ${extra.trim()}` : "";
  // El tipo va siempre: el brief de un ejemplo lo complementa, no lo sustituye.
  const base = exampleBrief.trim() ? `${TIER_PROMPT[tier]}. ${exampleBrief.trim()}` : TIER_PROMPT[tier];
  const end = (x: string) => (x && !/[.!?]$/.test(x) ? `${x}.` : x);
  const join = (b: string, sheet: string) => [head, end(b), traitText, end(extraText), sheet].filter(Boolean).join(" ");
  const full = join(base, SHEET);
  if (!maxLength || full.length <= maxLength) return full;
  // Lo obligatorio (foto, tipo, rasgos y hoja corta) se reserva; lo opcional (brief del ejemplo y descripción) se recorta.
  const fixed = [head, end(TIER_PROMPT[tier]), traitText, SHORT_SHEET].filter(Boolean).join(" ");
  let room = maxLength - fixed.length - 2;
  const fit = (x: string) => {
    if (room <= 20 || !x) return "";
    const out = x.length <= room ? x : x.slice(0, room).replace(/\s+\S*$/, "");
    room -= out.length + 1;
    return out;
  };
  const brief = fit(exampleBrief.trim());
  const extraFit = fit(extraText);
  const opt = [head, end(TIER_PROMPT[tier]), end(brief), traitText, end(extraFit), SHORT_SHEET].filter(Boolean).join(" ");
  return opt.slice(0, maxLength);
}

/** Elige al azar una opción permitida por grupo (las de varias, a veces ninguna), como el dado de Higgsfield. */
export function randomSelection(tier: Tier): Selection {
  const pick = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)];
  const sel: Selection = {};
  for (const grp of GROUPS) {
    const allowed = grp.options.filter((o) => o.tiers.includes(tier) && o.id !== "acc_none");
    if (!allowed.length) continue;
    if (grp.max > 1 && Math.random() < 0.5) continue;
    sel[grp.id] = [pick(allowed).id];
  }
  return sel;
}
