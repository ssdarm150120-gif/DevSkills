// Presentación del proyecto (pptxgenjs, deck estructurado). La genera la skill devskills:generar-presentacion.
//
// Uso (desde documentacion/presentacion/):
//   npm install            (una sola vez: instala las dependencias de package.json en ./node_modules)
//   node generar_presentacion.js [datos_presentacion.json] [salida.pptx]
//
// Todo el contenido sale de datos_presentacion.json (lo llena el analista a partir del SRS y del PLAN).
// La diapositiva de tipo "plan" lee las fechas de las entregas de ../PLAN.md (tabla generada por
// plan_sprints.py) si el JSON no las trae. La salida queda junto a este archivo, con ruta relativa.
// Dependencias: pptxgenjs, react, react-dom, react-icons, sharp (jszip viene con pptxgenjs).
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const Fi = require("react-icons/fi");

const DATOS_RUTA = path.resolve(__dirname, process.argv[2] || "datos_presentacion.json");
const D = JSON.parse(fs.readFileSync(DATOS_RUTA, "utf8"));
const nombreArchivo = (t) => String(t).normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "") || "Proyecto";
const SALIDA = path.resolve(__dirname, process.argv[3] || `${nombreArchivo(D.proyecto)}_Propuesta_v${D.version || 1}.pptx`);

const THEME = {
  name: D.proyecto,
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: Object.assign({
    dk1: "1F2A30", lt1: "FFFFFF", dk2: "0E2A31", lt2: "F1F5F4",
    accent1: "0F4C5C", accent2: "E9A23B", accent3: "2E7D6B", accent4: "B5523F",
    accent5: "5B7A82", accent6: "CFE3E1", hlink: "0F4C5C", folHlink: "5B7A82",
  }, D.colores || {}),
};

// ---------- tema (mínimo de applyTheme, incorporado para no depender de una skill externa) ----------
// pptxgenjs fija la paleta de Office en theme1.xml; aquí se escribe la del proyecto.
const SLOTS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"];
async function applyTheme(deckPath, theme) {
  const JSZip = require(require.resolve("jszip", { paths: [require.resolve("pptxgenjs")] }));
  const zip = await JSZip.loadAsync(fs.readFileSync(deckPath));
  const parte = "ppt/theme/theme1.xml";
  for (const k of SLOTS) {
    if (!/^[0-9A-Fa-f]{6}$/.test(String(theme.colors[k]))) throw new Error(`Color de tema inválido: ${k}`);
  }
  const nombre = String(theme.name).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const esquema = `<a:clrScheme name="${nombre}">` + SLOTS.map((k) => `<a:${k}><a:srgbClr val="${theme.colors[k].toUpperCase()}"/></a:${k}>`).join("") + "</a:clrScheme>";
  const xml = (await zip.file(parte).async("string"))
    .replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => esquema)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, cab) => `${cab}${nombre}"`);
  zip.file(parte, xml);
  fs.writeFileSync(deckPath, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

const K = THEME.colors;
const SUAVE = "4A5568";      // texto secundario sobre claro
const SUAVE_OSC = "CFE3E1";  // texto secundario sobre oscuro
const BORDE = "D9E2E0";
const color = (c) => (c && K[c]) || c || K.accent1;  // acepta "accent2" o un hex

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.author = D.autor || "";
pres.title = `${D.proyecto}: ${D.subtitulo_documento || "propuesta del proyecto"}`;
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

// ---------- íconos (nombres de react-icons/fi, por ejemplo "FiCalendar") ----------
async function icono(nombre, colorIcono = "#FFFFFF") {
  const Comp = Fi[nombre] || Fi.FiCircle;
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: colorIcono, size: 256, strokeWidth: 2 }));
  const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
async function iconoEnCirculo(slide, nombre, x, y, d, fondo, colorIcono = "#FFFFFF") {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fondo }, line: { color: fondo }, objectName: `circulo-${nombre}` });
  const pad = d * 0.24;
  slide.addImage({ data: await icono(nombre, colorIcono), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad, altText: nombre });
}
const sombra = () => ({ type: "outer", color: "0E2A31", opacity: 0.12, blur: 6, offset: 2, angle: 90 });

// ---------- layouts ----------
const pie = (c) => ({ text: { text: `${D.proyecto} · ${D.pie || "Propuesta del proyecto"}`, options: { x: 0.5, y: 5.22, w: 6, h: 0.25, fontSize: 10, color: c, margin: 0, isTextBox: true } } });
pres.defineSlideMaster({
  title: "PORTADA", background: { color: K.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", align: "left", x: 0.6, y: 1.55, w: 8.8, h: 1.0, fontSize: 54, bold: true, color: K.lt1, valign: "top", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 2.65, w: 8.4, h: 1.2, fontSize: 24, color: SUAVE_OSC, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CIERRE", background: { color: K.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", align: "left", x: 0.6, y: 1.2, w: 8.8, h: 1.9, fontSize: 44, bold: true, color: K.lt1, valign: "top", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.35, w: 8.4, h: 1.0, fontSize: 20, color: SUAVE_OSC, valign: "top", margin: 0 }, text: "" } },
  ],
});
for (const [nombre, fondo, titulo, texto] of [["CONTENIDO_CLARO", K.lt1, K.dk2, SUAVE], ["CONTENIDO_TINTE", K.lt2, K.dk2, SUAVE], ["CONTENIDO_OSCURO", K.dk2, K.lt1, SUAVE_OSC]]) {
  pres.defineSlideMaster({
    title: nombre, background: { color: fondo },
    objects: [
      { placeholder: { options: { name: "title", type: "title", align: "left", x: 0.5, y: 0.32, w: 9.0, h: 0.7, fontSize: 30, bold: true, color: titulo, valign: "middle", margin: 0 }, text: "" } },
      pie(texto),
    ],
    slideNumber: { x: 9.1, y: 5.22, w: 0.4, h: 0.25, fontSize: 10, color: texto, align: "right" },
  });
}
pres.defineSlideMaster({
  title: "ENUNCIADO", background: { color: K.accent1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", align: "left", x: 0.5, y: 0.45, w: 9.0, h: 1.2, fontSize: 32, bold: true, color: K.lt1, valign: "top", margin: 0 }, text: "" } },
    pie(SUAVE_OSC),
  ],
  slideNumber: { x: 9.1, y: 5.22, w: 0.4, h: 0.25, fontSize: 10, color: SUAVE_OSC, align: "right" },
});

const T = (slide, text, o) => slide.addText(text, Object.assign({ isTextBox: true, margin: 0, fontFace: THEME.bodyFontFace, valign: "top" }, o));
function tarjeta(slide, x, y, w, h, fill = K.lt1, borde = BORDE, nombre = "tarjeta") {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: borde, width: 0.75 }, shadow: sombra(), objectName: nombre });
}
const vinetas = (lista) => lista.map((t, j, a) => ({ text: t, options: { bullet: true, breakLine: j < a.length - 1 } }));
function nota(slide, texto, y = 4.05, h = 0.8) {
  if (!texto) return;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5, y, w: 9.0, h, rectRadius: 0.08, fill: { color: "FCF1DE" }, line: { color: "FCF1DE" }, objectName: "conclusion" });
  T(slide, texto, { x: 0.75, y: y + 0.05, w: 8.5, h: h - 0.1, fontSize: 15, bold: true, color: K.dk2, valign: "middle" });
}

// ---------- plan: entregas desde PLAN.md (tabla resumen generada por plan_sprints.py) ----------
function entregasDelPlan() {
  const plan = path.resolve(__dirname, "..", "PLAN.md");
  if (!fs.existsSync(plan)) return [];
  const filas = [];
  const re = /^\| ([0-9]+[a-z]?) \| ([^|]+) \| \d+ \| [^|]+ \| S\d+ a S\d+ \| (\d\d)\/(\d\d)\/(\d{4}) a (\d\d)\/(\d\d)\/(\d{4}) \|$/gm;
  let m;
  while ((m = re.exec(fs.readFileSync(plan, "utf8")))) {
    filas.push({ nombre: `${m[1]} · ${m[2].trim()}`, inicio: `${m[5]}-${m[4]}-${m[3]}`, fin: `${m[8]}-${m[7]}-${m[6]}`, valor: false });
  }
  return filas;
}
const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

// ---------- tipos de diapositiva ----------
const TIPOS = {
  async portada(s, d) {
    if (d.etiqueta) T(s, d.etiqueta, { x: 0.6, y: 1.05, w: 8, h: 0.35, fontSize: 14, bold: true, color: K.accent2, charSpacing: 3 });
    s.addText(d.titulo || D.proyecto, { placeholder: "title" });
    s.addText(d.subtitulo || "", { placeholder: "body" });
    if (d.linea) {
      await iconoEnCirculo(s, d.icono || "FiMessageCircle", 0.6, 4.05, 0.6, K.accent1);
      T(s, d.linea, { x: 1.35, y: 4.17, w: 7.5, h: 0.4, fontSize: 16, color: SUAVE_OSC, valign: "middle" });
    }
    if (d.firma) T(s, d.firma, { x: 0.6, y: 5.05, w: 6, h: 0.3, fontSize: 12, color: SUAVE_OSC });
  },
  // 3 tarjetas con ícono (por ejemplo, el problema). La última puede ir resaltada.
  async tarjetas(s, d) {
    const n = Math.min(d.tarjetas.length, 3);
    for (let i = 0; i < n; i++) {
      const [ic, tit, txt] = d.tarjetas[i];
      const x = 0.5 + i * 3.05;
      tarjeta(s, x, 1.35, 2.85, 3.4, K.lt1, BORDE, `tarjeta-${i}`);
      await iconoEnCirculo(s, ic, x + 0.3, 1.65, 0.65, d.resaltar === i ? K.accent4 : K.accent1);
      T(s, tit, { x: x + 0.3, y: 2.5, w: 2.3, h: 0.45, fontSize: 20, bold: true, color: K.dk2 });
      T(s, txt, { x: x + 0.3, y: 3.0, w: 2.3, h: 1.6, fontSize: 15, color: SUAVE });
    }
  },
  // 4 cifras grandes (línea base medida)
  async cifras(s, d) {
    for (let i = 0; i < Math.min(d.cifras.length, 4); i++) {
      const x = 0.5 + (i % 2) * 4.6, y = 1.25 + Math.floor(i / 2) * 1.85;
      T(s, d.cifras[i][0], { x, y, w: 4.3, h: 0.85, fontSize: 48, bold: true, color: d.resaltar === i ? K.accent2 : K.lt1 });
      T(s, d.cifras[i][1], { x, y: y + 0.85, w: 4.2, h: 0.8, fontSize: 15, color: SUAVE_OSC });
    }
    if (d.fuente) T(s, d.fuente, { x: 0.5, y: 4.95, w: 8.5, h: 0.25, fontSize: 10, color: SUAVE_OSC, italic: true });
  },
  // hasta 4 pasos con flechas y una conclusión (la causa)
  async flujo(s, d) {
    const n = Math.min(d.pasos.length, 4);
    for (let i = 0; i < n; i++) {
      const [ic, tit, txt] = d.pasos[i];
      const x = 0.5 + i * 2.35;
      tarjeta(s, x, 1.5, 1.95, 2.2, i === n - 1 ? K.lt2 : K.lt1, BORDE, `flujo-${i}`);
      await iconoEnCirculo(s, ic, x + 0.68, 1.72, 0.6, K.accent1);
      T(s, tit, { x: x + 0.1, y: 2.45, w: 1.75, h: 0.4, fontSize: 18, bold: true, color: K.dk2, align: "center" });
      T(s, txt, { x: x + 0.12, y: 2.9, w: 1.71, h: 0.75, fontSize: 13, color: SUAVE, align: "center" });
      if (i < n - 1) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.0, y: 2.45, w: 0.3, h: 0.3, fill: { color: K.accent2 }, line: { color: K.accent2 }, objectName: `flecha-${i}` });
    }
    nota(s, d.conclusion);
  },
  // enunciado con 3 pilares (la solución)
  async pilares(s, d) {
    for (let i = 0; i < Math.min(d.pilares.length, 3); i++) {
      const [ic, tit, txt] = d.pilares[i];
      const x = 0.5 + i * 3.05;
      tarjeta(s, x, 2.0, 2.85, 2.75, "134F5E", "2C6878", `pilar-${i}`);
      await iconoEnCirculo(s, ic, x + 0.3, 2.3, 0.6, K.accent2, "#0E2A31");
      T(s, tit, { x: x + 0.3, y: 3.05, w: 2.3, h: 0.45, fontSize: 22, bold: true, color: K.lt1 });
      T(s, txt, { x: x + 0.3, y: 3.55, w: 2.3, h: 1.1, fontSize: 14, color: SUAVE_OSC });
    }
  },
  // gráfica de barras a la izquierda, 2 tarjetas a la derecha y una nota (segmentos)
  async grafica(s, d) {
    s.addChart(pres.charts.BAR, [{ name: d.serie || d.titulo_grafica || "", labels: d.etiquetas, values: d.valores }], {
      x: 0.5, y: 1.15, w: 4.4, h: 2.65, barDir: "col", barGapWidthPct: 45,
      chartColors: [K.accent1, K.accent2, "F2C679", "F7DFB0"],
      showTitle: !!d.titulo_grafica, title: d.titulo_grafica || "", titleFontSize: 12, titleColor: K.dk2, titleFontFace: "+mn-lt",
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: K.dk1, dataLabelFontBold: true, dataLabelFontFace: "+mn-lt",
      catAxisLabelColor: SUAVE, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt",
      valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false,
      valAxisMaxVal: Math.ceil(Math.max(...d.valores) * 1.2), valAxisMinVal: 0,
    });
    if (d.aclaracion) T(s, d.aclaracion, { x: 0.5, y: 3.82, w: 4.4, h: 0.3, fontSize: 10, italic: true, color: SUAVE });
    for (let i = 0; i < Math.min((d.tarjetas || []).length, 2); i++) {
      const [ic, tit, txt] = d.tarjetas[i];
      const y = 1.2 + i * 1.5;
      tarjeta(s, 5.2, y, 4.3, 1.35, K.lt1, BORDE, `segmento-${i}`);
      await iconoEnCirculo(s, ic, 5.4, y + 0.2, 0.55, i === 1 ? K.accent2 : K.accent1, i === 1 ? "#0E2A31" : "#FFFFFF");
      T(s, tit, { x: 6.15, y: y + 0.15, w: 3.2, h: 0.35, fontSize: 16, bold: true, color: K.dk2 });
      T(s, txt, { x: 6.15, y: y + 0.52, w: 3.25, h: 0.78, fontSize: 12, color: SUAVE });
    }
    if (d.nota) {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5, y: 4.2, w: 9.0, h: 0.85, rectRadius: 0.08, fill: { color: "FCF1DE" }, line: { color: "FCF1DE" }, objectName: "nota-grafica" });
      T(s, d.nota, { x: 0.75, y: 4.25, w: 8.5, h: 0.75, fontSize: 13, color: K.dk2, valign: "middle" });
    }
  },
  // línea de tiempo de hasta 5 pasos (un recorrido de punta a punta)
  async recorrido(s, d) {
    const n = Math.min(d.pasos.length, 5);
    s.addShape(pres.shapes.LINE, { x: 0.95, y: 1.95, w: 8.1, h: 0, line: { color: BORDE, width: 2 }, objectName: "linea-tiempo" });
    for (let i = 0; i < n; i++) {
      const x = 0.5 + i * 1.82;
      s.addShape(pres.shapes.OVAL, { x: x + 0.47, y: 1.6, w: 0.7, h: 0.7, fill: { color: i === n - 1 ? K.accent3 : K.accent1 }, line: { color: K.lt1, width: 2 }, objectName: `paso-${i}` });
      T(s, String(i + 1), { x: x + 0.47, y: 1.6, w: 0.7, h: 0.7, fontSize: 20, bold: true, color: K.lt1, align: "center", valign: "middle" });
      T(s, d.pasos[i][0], { x, y: 2.5, w: 1.65, h: 0.4, fontSize: 16, bold: true, color: K.dk2, align: "center" });
      T(s, d.pasos[i][1], { x: x + 0.02, y: 2.95, w: 1.61, h: 1.3, fontSize: 13, color: SUAVE, align: "center" });
    }
    if (d.pie_texto) T(s, d.pie_texto, { x: 0.5, y: 4.6, w: 9, h: 0.35, fontSize: 14, italic: true, color: K.accent1, align: "center" });
  },
  // 5 beneficios: 3 arriba y 2 abajo
  async beneficios(s, d) {
    for (let i = 0; i < Math.min(d.beneficios.length, 5); i++) {
      const [ic, tit, txt] = d.beneficios[i];
      const arriba = i < 3;
      const w = arriba ? 2.85 : 4.4;
      const x = arriba ? 0.5 + i * 3.075 : 0.5 + (i - 3) * 4.6;
      const y = arriba ? 1.2 : 3.2;
      const h = arriba ? 1.85 : 1.55;
      tarjeta(s, x, y, w, h, K.lt1, BORDE, `beneficio-${i}`);
      await iconoEnCirculo(s, ic, x + 0.25, y + 0.22, 0.5, K.accent1);
      T(s, tit, { x: x + 0.9, y: y + 0.22, w: w - 1.1, h: 0.5, fontSize: 16, bold: true, color: K.dk2, valign: "middle" });
      T(s, txt, { x: x + 0.25, y: y + 0.85, w: w - 0.5, h: h - 0.95, fontSize: 13, color: SUAVE });
    }
  },
  // cuadrícula de hasta 12 módulos (4 x 3)
  async modulos(s, d) {
    for (let i = 0; i < Math.min(d.modulos.length, 12); i++) {
      const [ic, tit, txt] = d.modulos[i];
      const c = i % 4, r = Math.floor(i / 4);
      const x = 0.5 + c * 2.28, y = 1.2 + r * 1.27;
      tarjeta(s, x, y, 2.12, 1.12, K.lt1, BORDE, `modulo-${i}`);
      await iconoEnCirculo(s, ic, x + 0.12, y + 0.2, 0.4, K.accent1);
      T(s, tit, { x: x + 0.6, y: y + 0.15, w: 1.47, h: 0.5, fontSize: 12, bold: true, color: K.dk2, valign: "middle" });
      T(s, txt, { x: x + 0.15, y: y + 0.72, w: 1.9, h: 0.32, fontSize: 11, color: SUAVE });
    }
  },
  // 2 bloques con viñetas
  async bloques(s, d) {
    for (let i = 0; i < Math.min(d.bloques.length, 2); i++) {
      const [ic, tit, lista] = d.bloques[i];
      const x = 0.5 + i * 4.6;
      tarjeta(s, x, 1.25, 4.4, 3.2, K.lt1, BORDE, `bloque-${i}`);
      await iconoEnCirculo(s, ic, x + 0.3, 1.5, 0.6, i === 0 ? K.accent1 : K.accent3);
      T(s, tit, { x: x + 1.1, y: 1.5, w: 3.1, h: 0.6, fontSize: 16, bold: true, color: K.dk2, valign: "middle" });
      T(s, vinetas(lista), { x: x + 0.3, y: 2.3, w: 3.85, h: 2.4, fontSize: 14, color: SUAVE, paraSpaceAfter: 6 });
    }
  },
  // 4 reglas sobre fondo oscuro
  async reglas(s, d) {
    for (let i = 0; i < Math.min(d.reglas.length, 4); i++) {
      const [ic, tit, txt] = d.reglas[i];
      const x = 0.5 + (i % 2) * 4.6, y = 1.2 + Math.floor(i / 2) * 1.9;
      tarjeta(s, x, y, 4.4, 1.72, "163A43", "2C5560", `regla-${i}`);
      await iconoEnCirculo(s, ic, x + 0.25, y + 0.25, 0.55, K.accent2, "#0E2A31");
      T(s, tit, { x: x + 1.0, y: y + 0.25, w: 3.2, h: 0.4, fontSize: 18, bold: true, color: K.lt1 });
      T(s, txt, { x: x + 1.0, y: y + 0.7, w: 3.25, h: 0.95, fontSize: 13, color: SUAVE_OSC });
    }
  },
  // guion de la demo (hasta 7 pasos) y panel con el enlace a la maqueta
  async demo(s, d) {
    for (let i = 0; i < Math.min(d.guion.length, 7); i++) {
      const y = 1.25 + i * 0.52;
      s.addShape(pres.shapes.OVAL, { x: 0.5, y, w: 0.38, h: 0.38, fill: { color: K.accent1 }, line: { color: K.accent1 }, objectName: `guion-${i}` });
      T(s, String(i + 1), { x: 0.5, y, w: 0.38, h: 0.38, fontSize: 13, bold: true, color: K.lt1, align: "center", valign: "middle" });
      T(s, d.guion[i], { x: 1.05, y, w: 4.0, h: 0.38, fontSize: 15, color: K.dk2, valign: "middle" });
    }
    tarjeta(s, 5.5, 1.25, 4.0, 3.55, K.lt2, BORDE, "panel-demo");
    await iconoEnCirculo(s, "FiSmartphone", 5.8, 1.5, 0.6, K.accent1);
    T(s, d.panel_titulo || "Maqueta en Figma", { x: 6.55, y: 1.6, w: 2.8, h: 0.4, fontSize: 18, bold: true, color: K.dk2, valign: "middle" });
    T(s, d.enlace || "[Enlace a la maqueta de Figma]", { x: 5.8, y: 2.3, w: 3.5, h: 0.4, fontSize: 14, bold: true, color: K.accent4 });
    T(s, vinetas(d.panel || []), { x: 5.8, y: 2.8, w: 3.5, h: 1.8, fontSize: 14, color: SUAVE, paraSpaceAfter: 6 });
  },
  // tabla de metas: indicador, hoy (medido), meta (SRS 1.1.1)
  async metas(s, d) {
    const h = { bold: true, color: K.lt1, fill: { color: K.accent1 }, fontSize: 14 };
    const filas = [[{ text: "Indicador", options: h }, { text: "Hoy (medido)", options: h }, { text: "Meta", options: h }]]
      .concat(d.metas.map((f, i) => f.map((c, j) => ({ text: c, options: { fontSize: 13, color: j === 2 ? K.accent3 : K.dk1, bold: j === 2, fill: { color: (i + 1) % 2 ? K.lt1 : K.lt2 } } }))));
    s.addTable(filas, { x: 0.5, y: 1.2, w: 9.0, colW: [4.4, 2.0, 2.6], rowH: 0.44, border: { type: "solid", pt: 0.75, color: BORDE }, valign: "middle", margin: 0.08 });
    if (d.aclaracion) T(s, d.aclaracion, { x: 0.5, y: 4.45, w: 9, h: 0.5, fontSize: 12, italic: true, color: SUAVE });
  },
  // 4 tarjetas altas (bases sobre las que se construye)
  async bases(s, d) {
    for (let i = 0; i < Math.min(d.bases.length, 4); i++) {
      const [ic, tit, txt] = d.bases[i];
      const x = 0.5 + i * 2.28;
      tarjeta(s, x, 1.3, 2.12, 3.45, K.lt1, BORDE, `base-${i}`);
      await iconoEnCirculo(s, ic, x + 0.25, 1.55, 0.6, K.accent1);
      T(s, tit, { x: x + 0.25, y: 2.35, w: 1.7, h: 0.6, fontSize: 16, bold: true, color: K.dk2 });
      T(s, txt, { x: x + 0.25, y: 3.0, w: 1.7, h: 1.65, fontSize: 13, color: SUAVE });
    }
  },
  // Gantt simple de entregas por mes (de d.entregas o de PLAN.md)
  async plan(s, d) {
    const ent = (d.entregas && d.entregas.length ? d.entregas : entregasDelPlan()).slice(0, 7);
    if (!ent.length) { T(s, "Sin entregas planificadas todavía (PLAN.md).", { x: 0.5, y: 2.4, w: 9, h: 0.5, fontSize: 16, color: SUAVE, align: "center" }); return; }
    const fechaDe = (t) => new Date(t + "T00:00:00");
    const ini = fechaDe(ent[0].inicio), finU = fechaDe(ent[ent.length - 1].fin);
    const inicio = new Date(ini.getFullYear(), ini.getMonth(), 1), fin = new Date(finU.getFullYear(), finU.getMonth() + 1, 0);
    const meses = [];
    for (let m = new Date(inicio); m <= fin; m = new Date(m.getFullYear(), m.getMonth() + 1, 1)) meses.push(new Date(m));
    const x0 = 3.7, ancho = 5.8, mes = ancho / meses.length;
    meses.forEach((m, i) => T(s, MESES[m.getMonth()], { x: x0 + i * mes, y: 1.15, w: mes, h: 0.28, fontSize: meses.length > 18 ? 7 : 10, color: SUAVE, align: "center" }));
    let k = 0;
    while (k < meses.length) {
      const anio = meses[k].getFullYear();
      let j = k;
      while (j < meses.length && meses[j].getFullYear() === anio) j++;
      T(s, String(anio), { x: x0 + k * mes, y: 0.93, w: (j - k) * mes, h: 0.22, fontSize: 10, bold: true, color: SUAVE, align: "center" });
      k = j;
    }
    const pos = (f) => x0 + ancho * (f - inicio) / (fin - inicio);
    ent.forEach((e, i) => {
      const y = 1.5 + i * 0.47;
      const col = e.valor ? K.accent1 : K.accent5;
      if (i % 2 === 0) s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: y - 0.04, w: 9.0, h: 0.45, fill: { color: K.lt2 }, line: { color: K.lt2 }, objectName: `fila-${i}` });
      T(s, e.nombre, { x: 0.6, y, w: 3.05, h: 0.37, fontSize: 12, bold: !!e.valor, color: K.dk2, valign: "middle" });
      const da = fechaDe(e.inicio), db = fechaDe(e.fin);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: pos(da), y: y + 0.06, w: Math.max(0.12, pos(db) - pos(da)), h: 0.25, rectRadius: 0.05, fill: { color: col }, line: { color: col }, objectName: `barra-${i}` });
    });
    if (d.pie_texto) T(s, d.pie_texto, { x: 0.5, y: 4.82, w: 9, h: 0.35, fontSize: 11, italic: true, color: SUAVE });
  },
  // 4 cifras del método de trabajo sobre fondo oscuro y una nota
  async metodo(s, d) {
    for (let i = 0; i < Math.min(d.metodo.length, 4); i++) {
      const x = 0.5 + i * 2.28;
      T(s, d.metodo[i][0], { x, y: 1.55, w: 2.15, h: 0.8, fontSize: 30, bold: true, color: i === 3 ? K.accent2 : K.lt1 });
      T(s, d.metodo[i][1], { x, y: 2.4, w: 2.0, h: 1.0, fontSize: 14, color: SUAVE_OSC });
    }
    if (d.nota) {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5, y: 3.75, w: 9.0, h: 0.85, rectRadius: 0.08, fill: { color: "163A43" }, line: { color: "2C5560" }, objectName: "nota-metodo" });
      T(s, d.nota, { x: 0.75, y: 3.85, w: 8.5, h: 0.65, fontSize: 14, color: K.lt1, valign: "middle" });
    }
  },
  // lo que se necesita para arrancar (lista) y costos (tabla)
  async necesitamos(s, d) {
    T(s, d.titulo_lista || "Decisiones y accesos", { x: 0.5, y: 1.2, w: 4.3, h: 0.4, fontSize: 18, bold: true, color: K.dk2 });
    for (let i = 0; i < Math.min(d.lista.length, 5); i++) {
      const y = 1.75 + i * 0.6;
      await iconoEnCirculo(s, "FiCheck", 0.5, y, 0.36, K.accent3);
      T(s, d.lista[i], { x: 1.0, y: y - 0.02, w: 3.9, h: 0.42, fontSize: 14, color: K.dk1, valign: "middle" });
    }
    if (d.costos && d.costos.length) {
      T(s, d.titulo_costos || "Costo operativo estimado (mensual)", { x: 5.3, y: 1.2, w: 4.2, h: 0.4, fontSize: 18, bold: true, color: K.dk2 });
      const hi = { bold: true, color: K.lt1, fill: { color: K.accent1 }, fontSize: 13 };
      const ult = d.costos.length;
      const inv = [[{ text: "Concepto", options: hi }, { text: "Monto", options: hi }]]
        .concat(d.costos.map((f, i) => f.map((c, j) => ({ text: c, options: { fontSize: 12, color: j === 1 ? K.accent3 : K.dk1, bold: i + 1 === ult, fill: { color: (i + 1) % 2 ? K.lt1 : K.lt2 } } }))));
      s.addTable(inv, { x: 5.3, y: 1.75, w: 4.2, colW: [3.0, 1.2], rowH: 0.42, border: { type: "solid", pt: 0.75, color: BORDE }, valign: "middle", margin: 0.06 });
      if (d.aclaracion) T(s, d.aclaracion, { x: 5.3, y: 4.75, w: 4.2, h: 0.4, fontSize: 10, italic: true, color: SUAVE });
    }
  },
  async cierre(s, d) {
    s.addText(d.titulo, { placeholder: "title" });
    s.addText(d.subtitulo || "", { placeholder: "body" });
    if (d.firma) T(s, d.firma, { x: 0.6, y: 5.05, w: 6, h: 0.3, fontSize: 12, color: SUAVE_OSC });
  },
};
const MAESTRO = {
  portada: "PORTADA", cierre: "CIERRE", pilares: "ENUNCIADO", cifras: "CONTENIDO_OSCURO", reglas: "CONTENIDO_OSCURO",
  metodo: "CONTENIDO_OSCURO", recorrido: "CONTENIDO_TINTE", modulos: "CONTENIDO_TINTE", bases: "CONTENIDO_TINTE",
};

(async () => {
  const secciones = new Set();
  for (const d of D.diapositivas) {
    const dibujar = TIPOS[d.tipo];
    if (!dibujar) throw new Error(`Tipo de diapositiva desconocido: ${d.tipo}`);
    const seccion = d.seccion || "Presentación";
    if (!secciones.has(seccion)) { pres.addSection({ title: seccion }); secciones.add(seccion); }
    const s = pres.addSlide({ masterName: d.maestro || MAESTRO[d.tipo] || "CONTENIDO_CLARO", sectionTitle: seccion });
    if (d.titulo && !["portada", "cierre"].includes(d.tipo)) s.addText(d.titulo, { placeholder: "title" });
    await dibujar(s, d);
    if (d.notas) s.addNotes(d.notas);
  }
  await pres.writeFile({ fileName: SALIDA });
  await applyTheme(SALIDA, THEME);
  console.log("Generado:", path.relative(process.cwd(), SALIDA));
})().catch((e) => { console.error(e); process.exit(1); });
