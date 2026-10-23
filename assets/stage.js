// baryonengine.com: the opening stage. Optional: without it the page shows the static relief.
// The valley's relief is lit live from the engine's own terrain (an 8 m heightmap made by
// tools/relief.py from the sealed lidar tiles), by the static relief's own method: Horn's
// 3 x 3 slope kernel and grey 24 + 231 * max(0, cos). The light is a lamp moved as you
// scroll, not the sun. It draws only on scroll, on resize and for the 2.6 s dawn; it never
// loops on its own. If anything fails, the page stays exactly as it was. No network use.

const MAP_W = 15000, MAP_H = 8000;              // metres; x east from the west edge, y south from the north edge
const FOCUS = { x: 6150, y: 4300 };             // the camp and the lake's east end, where the frames were taken
const DAWN_MS = 2600;
const stage = document.querySelector(".stage");
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const saveData = navigator.connection && navigator.connection.saveData;

if (stage && !reduced && !saveData) start();

function start() {
  const canvas = stage.querySelector(".map-gl");
  const svg = stage.querySelector(".map-svg");
  const readout = stage.querySelector("[data-light]");
  const gl = canvas.getContext("webgl", { antialias: false, alpha: false });
  if (!gl) return;

  const vs = `attribute vec2 a; varying vec2 v;
    void main() { v = vec2(a.x * .5 + .5, .5 - a.y * .5); gl_Position = vec4(a, 0., 1.); }`;
  const fs = `#ifdef GL_FRAGMENT_PRECISION_HIGH
    precision highp float;
    #else
    precision mediump float;
    #endif
    uniform sampler2D h; uniform vec2 size; uniform vec4 view; uniform vec3 light; uniform float cell;
    varying vec2 v;
    vec4 px(vec2 t) { return texture2D(h, (clamp(t, vec2(0.), size - 1.) + .5) / size); }
    float at(vec2 t) { vec4 c = px(t); return (c.r * 65280. + c.g * 255.) * .05; }
    float bil(vec2 p) {
      vec2 i = floor(p - .5), f = fract(p - .5);
      return mix(mix(at(i), at(i + vec2(1., 0.)), f.x), mix(at(i + vec2(0., 1.)), at(i + vec2(1.)), f.x), f.y);
    }
    void main() {
      vec2 p = (view.xy + v * view.zw) * size;
      vec2 i = floor(p - .5), f = fract(p - .5);
      float w = mix(mix(px(i).b, px(i + vec2(1., 0.)).b, f.x), mix(px(i + vec2(0., 1.)).b, px(i + vec2(1.)).b, f.x), f.y);
      if (w > .5) { gl_FragColor = vec4(0., 0., 0., 1.); return; }
      // Horn (1981), as tools/relief.py: a b c / d . f / g h i, rows north to south.
      float a = bil(p + vec2(-1., -1.)), b = bil(p + vec2(0., -1.)), c = bil(p + vec2(1., -1.));
      float d = bil(p + vec2(-1., 0.)),                               ff = bil(p + vec2(1., 0.));
      float g = bil(p + vec2(-1., 1.)),  hh = bil(p + vec2(0., 1.)),  ii = bil(p + vec2(1., 1.));
      float east = ((c + 2. * ff + ii) - (a + 2. * d + g)) / (8. * cell);
      float south = ((g + 2. * hh + ii) - (a + 2. * b + c)) / (8. * cell);
      float s = max(0., dot(normalize(vec3(-east, south, 1.)), light));
      gl_FragColor = vec4(vec3((24. + 231. * s) / 255.), 1.);
    }`;
  const prog = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src); gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) return;
    gl.attachShader(prog, sh);
  }
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
  gl.useProgram(prog);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "a");
  gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const u = name => gl.getUniformLocation(prog, name);

  let ready = false, live = false, born = 0, pending = false;
  const ease = t => t < 0 ? 0 : t > 1 ? 1 : t * t * (3 - 2 * t);

  const img = new Image();
  img.decoding = "async";
  const base = document.documentElement.lang === "ru" ? "../" : "";
  img.src = base + (innerWidth < 760 ? "media/relief/height-16m.png" : "media/relief/height-8m.png");
  img.onload = () => {
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
    for (const [k, val] of [[gl.TEXTURE_MIN_FILTER, gl.NEAREST], [gl.TEXTURE_MAG_FILTER, gl.NEAREST],
      [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, val);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, img);
    gl.uniform2f(u("size"), img.width, img.height);
    gl.uniform1f(u("cell"), MAP_W / img.width);
    ready = true; born = performance.now();
    draw(born);                                   // the first frame now, whatever the observers say
  };

  function progress() {
    if (!live) return 0;
    const r = stage.getBoundingClientRect();
    const span = r.height - innerHeight;
    return span > 0 ? Math.min(1, Math.max(0, -r.top / span)) : 0;
  }

  function resize() {
    const ratio = Math.min(devicePixelRatio || 1, innerWidth < 760 ? 1.25 : 1.5);
    const w = Math.round(canvas.clientWidth * ratio), h = Math.round(canvas.clientHeight * ratio);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h); }
  }

  function view(p) {
    const aspect = canvas.clientWidth / canvas.clientHeight;
    const cover = Math.min(MAP_W, MAP_H * aspect);
    const zoom = ease((p - .3) / .55);
    const target = innerWidth < 760 ? 1900 : 3400;
    const w = cover + (target - cover) * zoom, hgt = w / aspect;
    const start = { x: MAP_W / 2 + (aspect < 1 ? -1350 : 0), y: MAP_H / 2 };
    let cx = start.x + (FOCUS.x - start.x) * zoom, cy = start.y + (FOCUS.y - start.y) * zoom;
    cx = Math.min(MAP_W - w / 2, Math.max(w / 2, cx));
    cy = Math.min(MAP_H - hgt / 2, Math.max(hgt / 2, cy));
    return { x: cx - w / 2, y: cy - hgt / 2, w, h: hgt };
  }

  function draw(now) {
    pending = false;
    if (!ready) return;
    resize();
    const p = progress();
    const dawn = ease((now - born) / DAWN_MS);
    const az = 95 + 170 * p;
    const alt = 4 + (10 + 30 * Math.sin(Math.PI * p) - 4) * dawn;
    const ar = az * Math.PI / 180, er = alt * Math.PI / 180;
    gl.uniform3f(u("light"), Math.sin(ar) * Math.cos(er), Math.cos(ar) * Math.cos(er), Math.sin(er));
    const r = view(p);
    gl.uniform4f(u("view"), r.x / MAP_W, r.y / MAP_H, r.w / MAP_W, r.h / MAP_H);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (gl.getError() !== gl.NO_ERROR) return;    // leave the static page as it is
    if (!live) {                                  // only after a good frame: the tall stage, the live legend
      live = true;
      stage.classList.add("is-live", "is-lit");
      addEventListener("scroll", request, { passive: true });
      addEventListener("resize", request, { passive: true });
    }
    stage.style.setProperty("--p", p.toFixed(4));
    svg.setAttribute("viewBox", `${r.x.toFixed(1)} ${r.y.toFixed(1)} ${r.w.toFixed(1)} ${r.h.toFixed(1)}`);
    svg.style.setProperty("--k", (r.w / canvas.clientWidth).toFixed(4));
    if (readout) readout.textContent = document.documentElement.lang === "ru"
      ? `${Math.round(az % 360)}°, высота ${Math.round(alt)}°` : `${Math.round(az % 360)}° at ${Math.round(alt)}°`;
    if (now - born < DAWN_MS) request();          // the dawn is the only motion that runs by itself
  }

  function request() {
    if (!pending && ready) { pending = true; requestAnimationFrame(draw); }
  }
}
