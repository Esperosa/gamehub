from __future__ import annotations

import logging
import math
import time
from array import array
from typing import Sequence

from PySide6.QtCore import QElapsedTimer, QTimer, Qt
from PySide6.QtGui import QOpenGLContext, QSurfaceFormat
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLFramebufferObjectFormat,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from hub.animations import MetaballSimulation, ParticleSimulation


_log = logging.getLogger(__name__)

GL_TRIANGLES = 0x0004
GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_SCISSOR_TEST = 0x0C11
GL_STENCIL_TEST = 0x0B90
GL_BLEND = 0x0BE2
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE0 = 0x84C0
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_LINEAR = 0x2601
MAX_METABALLS = 32
MAX_PARTICLES = 112


VERTEX_SHADER_330 = """
#version 330 core
layout(location=0) in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""


FRAGMENT_SHADER_330 = """
#version 330 core
#define MAX_METABALLS 32
#define MAX_PARTICLES 112

uniform vec2 u_res;
uniform float u_time;
uniform int u_mode;
uniform int u_metaball_count;
uniform int u_particle_count;
uniform vec4 u_metaballs[MAX_METABALLS];
uniform vec4 u_particles[MAX_PARTICLES];

uniform vec3 u_cam_pos;
uniform vec3 u_cam_right;
uniform vec3 u_cam_up;
uniform vec3 u_cam_fwd;
uniform float u_cam_aspect;
uniform float u_cam_fov;

in vec2 v_uv;
out vec4 fragColor;

float saturate(float x) { return clamp(x, 0.0, 1.0); }

vec3 safe_normalize(vec3 v) {
    float l = length(v);
    return (l > 1e-6) ? (v / l) : vec3(0.0, 0.0, 1.0);
}

vec2 iso_uv(vec2 uv) {
    float min_dim = max(1.0, min(u_res.x, u_res.y));
    return vec2(
        (uv.x - 0.5) * (u_res.x / min_dim),
        (uv.y - 0.5) * (u_res.y / min_dim)
    );
}

vec3 base_background(vec2 uv, float t) {
    vec3 c0 = vec3(8.0, 10.0, 16.0) / 255.0;
    vec3 c1 = vec3(4.0, 6.0, 10.0) / 255.0;
    vec3 bg = mix(c0, c1, uv.y * 0.9 + uv.x * 0.1);

    vec2 cA = vec2(0.25 + 0.05 * sin(t * 0.22), 0.30 + 0.05 * cos(t * 0.18));
    vec2 cB = vec2(0.80 + 0.04 * cos(t * 0.17), 0.65 + 0.06 * sin(t * 0.14));
    vec2 cC = vec2(0.55 + 0.05 * sin(t * 0.11), 0.15 + 0.05 * cos(t * 0.13));

    float dA = length(uv - cA);
    float dB = length(uv - cB);
    float dC = length(uv - cC);
    bg += vec3(0.08, 0.16, 0.19) * exp(-dA * 3.2);
    bg += vec3(0.11, 0.08, 0.18) * exp(-dB * 2.8);
    bg += vec3(0.03, 0.16, 0.20) * exp(-dC * 3.6);

    float vignette = smoothstep(0.90, 0.25, length(uv - vec2(0.5)));
    bg *= vignette;
    return bg;
}

vec3 render_particles(vec2 uv, vec3 bg) {
    vec2 iso = iso_uv(uv);
    vec3 accum = vec3(0.0);
    float alpha_acc = 0.0;
    vec3 light = normalize(vec3(-0.38, -0.42, 0.82));
    vec3 view_dir = vec3(0.0, 0.0, 1.0);
    vec3 half_dir = normalize(light + view_dir);

    for (int i = 0; i < MAX_PARTICLES; ++i) {
        if (i >= u_particle_count) {
            break;
        }
        vec4 p = u_particles[i];
        vec2 p_iso = iso_uv(p.xy);
        float r = max(p.z, 0.0005);
        vec2 dv = iso - p_iso;
        float d = length(dv);
        float nr = d / r;
        float core = 1.0 - smoothstep(0.00, 0.72, nr);
        float body = 1.0 - smoothstep(0.26, 1.20, nr);
        float halo = 1.0 - smoothstep(0.82, 3.30, nr);
        float mist = exp(-nr * nr * 1.35);

        vec2 unit_xy = dv / max(r, 1e-6);
        float z = sqrt(max(0.0, 1.0 - dot(unit_xy, unit_xy)));
        vec3 n = normalize(vec3(-unit_xy.x * 0.95, -unit_xy.y * 0.95, z));
        float diff = max(dot(n, light), 0.0);
        float spec = pow(max(dot(n, half_dir), 0.0), 26.0);
        float fres = pow(1.0 - max(dot(n, view_dir), 0.0), 2.2);

        float density = clamp(p.w, 0.0, 1.0);
        float intensity = (core * 0.56 + body * 0.50 + halo * 0.86 + mist * 0.30) * density;
        vec3 base_col = mix(vec3(0.48, 0.74, 0.96), vec3(0.84, 0.95, 1.00), density);
        vec3 shaded = base_col * (0.40 + 0.76 * diff);
        shaded += vec3(0.44, 0.58, 0.72) * spec;
        shaded += vec3(0.10, 0.16, 0.26) * fres;
        accum += shaded * intensity;
        alpha_acc += intensity * 0.54;
    }

    float blend = clamp(alpha_acc, 0.0, 0.84);
    vec3 lit = bg + accum * 0.64;
    return mix(bg, lit, blend);
}

vec3 env_color(vec3 d) {
    d = safe_normalize(d);
    float t = clamp(d.y * 0.5 + 0.5, 0.0, 1.0);
    vec3 sky_top = vec3(0.52, 0.74, 1.06);
    vec3 sky_bot = vec3(0.04, 0.06, 0.09);
    vec3 col = mix(sky_bot, sky_top, pow(t, 1.2));
    vec3 sun_dir = normalize(vec3(-0.35, 0.66, 0.68));
    float sun = pow(max(dot(d, sun_dir), 0.0), 180.0);
    col += vec3(3.6, 3.3, 3.0) * sun;
    if (d.y < 0.0) {
        float g = clamp(-d.y, 0.0, 1.0);
        col = mix(col, vec3(0.05, 0.05, 0.06), g * 0.84);
    }
    return col;
}

vec4 field_grad(vec3 p) {
    float f = 0.0;
    vec3 g = vec3(0.0);
    for (int i = 0; i < MAX_METABALLS; ++i) {
        if (i >= u_metaball_count) {
            break;
        }
        vec3 c = u_metaballs[i].xyz;
        float r = u_metaballs[i].w;
        vec3 d = p - c;
        float r2 = r * r;
        float d2 = dot(d, d);
        float t = 1.0 - d2 / max(r2, 1e-6);
        if (t > 0.0) {
            float t2 = t * t;
            f += t2 * t;
            g += ((-6.0 * t2) / max(r2, 1e-6)) * d;
        }
    }
    return vec4(g, f);
}

vec3 safe_inv(vec3 v) {
    vec3 ad = abs(v);
    vec3 s = vec3(
        (v.x < 0.0) ? -1.0 : 1.0,
        (v.y < 0.0) ? -1.0 : 1.0,
        (v.z < 0.0) ? -1.0 : 1.0
    );
    return s / max(ad, vec3(1e-6));
}

bool ray_box(vec3 ro, vec3 rd, out float tmin, out float tmax) {
    vec3 inv = safe_inv(rd);
    vec3 t0 = (vec3(-1.0) - ro) * inv;
    vec3 t1 = (vec3(1.0) - ro) * inv;
    vec3 tsm = min(t0, t1);
    vec3 tbg = max(t0, t1);
    tmin = max(max(tsm.x, tsm.y), tsm.z);
    tmax = min(min(tbg.x, tbg.y), tbg.z);
    return tmax >= max(tmin, 0.0);
}

bool trace_segment(
    vec3 ro,
    vec3 rd,
    float tmin,
    float tmax,
    float iso_enter,
    float iso_exit,
    out float t_enter,
    out float t_exit,
    out vec3 n_enter
) {
    const int STEPS = 132;
    float step_len = (tmax - tmin) / float(STEPS);
    float t = tmin;
    vec4 fg = field_grad(ro + rd * t);
    float prev = fg.w;

    bool inside = (prev >= iso_enter);
    bool have_enter = false;
    t_enter = tmin;
    t_exit = tmax;

    if (inside) {
        have_enter = true;
        vec3 g0 = fg.xyz;
        float g0l = length(g0);
        n_enter = (g0l > 1e-5) ? (g0 / g0l) : safe_normalize(-rd);
    }

    for (int i = 0; i < STEPS; ++i) {
        t += step_len;
        float cur = field_grad(ro + rd * t).w;

        if (!inside && prev < iso_enter && cur >= iso_enter) {
            float a = t - step_len;
            float b = t;
            for (int k = 0; k < 10; ++k) {
                float m = 0.5 * (a + b);
                float fm = field_grad(ro + rd * m).w;
                if (fm >= iso_enter) {
                    b = m;
                } else {
                    a = m;
                }
            }
            t_enter = 0.5 * (a + b);
            vec3 p_enter = ro + rd * t_enter;
            vec3 g = field_grad(p_enter).xyz;
            float gl = length(g);
            n_enter = (gl > 1e-5) ? (g / gl) : safe_normalize(-rd);
            inside = true;
            have_enter = true;
        } else if (inside && prev >= iso_exit && cur < iso_exit) {
            float a = t - step_len;
            float b = t;
            for (int k = 0; k < 10; ++k) {
                float m = 0.5 * (a + b);
                float fm = field_grad(ro + rd * m).w;
                if (fm < iso_exit) {
                    b = m;
                } else {
                    a = m;
                }
            }
            t_exit = 0.5 * (a + b);
            return have_enter && (t_exit > t_enter);
        }

        prev = cur;
    }

    if (have_enter) {
        t_exit = tmax;
        return t_exit > t_enter;
    }
    return false;
}

vec3 fresnel_schlick(float cos_theta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(1.0 - cos_theta, 5.0);
}

float D_GGX(float NdotH, float a) {
    float a2 = a * a;
    float d = (NdotH * NdotH) * (a2 - 1.0) + 1.0;
    return a2 / (3.14159265 * d * d + 1e-6);
}

float G_Smith(float NdotV, float NdotL, float a) {
    float k = (a + 1.0);
    k = (k * k) / 8.0;
    float g1v = NdotV / (NdotV * (1.0 - k) + k);
    float g1l = NdotL / (NdotL * (1.0 - k) + k);
    return g1v * g1l;
}

vec3 ACESFilm(vec3 x) {
    x = max(x, vec3(0.0));
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

vec3 render_metaballs(vec2 uv, vec3 bg) {
    vec2 ndc = uv * 2.0 - 1.0;
    ndc.x *= u_cam_aspect;
    float tan_half = tan(u_cam_fov * 0.5);
    vec3 rd = safe_normalize(u_cam_fwd + ndc.x * u_cam_right * tan_half + ndc.y * u_cam_up * tan_half);
    vec3 ro = u_cam_pos;

    float tmin;
    float tmax;
    if (!ray_box(ro, rd, tmin, tmax)) {
        return bg;
    }

    float iso_enter = 0.28;
    float iso_exit = 0.23;
    float t_enter;
    float t_exit;
    vec3 n_hit;
    if (!trace_segment(ro, rd, tmin, tmax, iso_enter, iso_exit, t_enter, t_exit, n_hit)) {
        return bg;
    }

    vec3 N = safe_normalize(n_hit);
    vec3 V = safe_normalize(-rd);

    float thickness = max(0.02, t_exit - t_enter);

    float ior = 1.33;
    float F0s = pow((ior - 1.0) / (ior + 1.0), 2.0);
    vec3 F0 = vec3(F0s);
    float roughness = 0.075;
    float a = max(roughness * roughness, 0.001);
    float NdotV = saturate(dot(N, V));
    vec3 F = fresnel_schlick(NdotV, F0);

    vec3 R = reflect(-V, N);
    vec3 refl = env_color(R);
    vec3 Tdir = refract(-V, N, 1.0 / ior);
    vec3 refr = env_color(Tdir);

    float density = 1.9;
    vec3 sigmaA = vec3(1.25, 0.62, 0.30);
    vec3 transmittance = exp(-sigmaA * thickness * density);
    refr *= transmittance;

    vec3 L = safe_normalize(vec3(-0.35, 0.66, 0.68));
    vec3 H = safe_normalize(V + L);
    float NdotL = saturate(dot(N, L));
    float NdotH = saturate(dot(N, H));
    float VdotH = saturate(dot(V, H));
    float D = D_GGX(NdotH, a);
    float G = G_Smith(NdotV, NdotL, a);
    vec3 Fspec = fresnel_schlick(VdotH, F0);
    vec3 spec = (D * G * Fspec) / max(4.0 * NdotV * NdotL, 1e-5);
    vec3 direct_spec = spec * vec3(2.4, 2.3, 2.2) * NdotL;
    direct_spec = min(direct_spec, vec3(0.85));

    vec3 scatter = vec3(0.10, 0.24, 0.40) * (1.0 - transmittance) * 0.95;
    vec3 col = mix(refr, refl, F) + direct_spec + scatter;
    float rim = pow(1.0 - NdotV, 1.8);
    col += vec3(0.22, 0.30, 0.42) * rim;
    col += vec3(0.03, 0.05, 0.08);
    col += bg * 0.02;
    col = clamp(col, vec3(0.0), vec3(1.20));
    if (any(isnan(col)) || any(isinf(col))) {
        col = bg;
    }

    col = pow(clamp(col, vec3(0.0), vec3(1.0)), vec3(1.0 / 2.2));
    return col;
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_res.xy;
    vec3 bg = base_background(uv, u_time);

    if (u_mode == 0) {
        vec3 particles = render_particles(uv, bg);
        fragColor = vec4(particles, 1.0);
        return;
    }

    vec3 metaballs = render_metaballs(uv, bg);
    fragColor = vec4(metaballs, 1.0);
}
"""


BLIT_FRAGMENT_SHADER_330 = """
#version 330 core
uniform sampler2D u_tex;
in vec2 v_uv;
out vec4 fragColor;
void main() {
    vec3 c = texture(u_tex, v_uv).rgb;
    fragColor = vec4(c, 1.0);
}
"""


TEMPORAL_FRAGMENT_SHADER_330 = """
#version 330 core
uniform sampler2D u_curr_tex;
uniform sampler2D u_prev_tex;
uniform float u_alpha;
uniform int u_use_prev;
in vec2 v_uv;
out vec4 fragColor;
void main() {
    vec3 curr = texture(u_curr_tex, v_uv).rgb;
    vec3 outc = curr;
    if (u_use_prev == 1) {
        vec3 prev = texture(u_prev_tex, v_uv).rgb;
        outc = mix(prev, curr, clamp(u_alpha, 0.0, 1.0));
    }
    fragColor = vec4(outc, 1.0);
}
"""


VERTEX_SHADER_120 = """
#version 120
attribute vec2 in_pos;
varying vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""


FRAGMENT_SHADER_120 = (
    FRAGMENT_SHADER_330.replace("#version 330 core", "#version 120")
    .replace("in vec2 v_uv;", "varying vec2 v_uv;")
    .replace("out vec4 fragColor;\n", "")
    .replace("fragColor", "gl_FragColor")
)


BLIT_FRAGMENT_SHADER_120 = """
#version 120
uniform sampler2D u_tex;
varying vec2 v_uv;
void main() {
    vec3 c = texture2D(u_tex, v_uv).rgb;
    gl_FragColor = vec4(c, 1.0);
}
"""


TEMPORAL_FRAGMENT_SHADER_120 = """
#version 120
uniform sampler2D u_curr_tex;
uniform sampler2D u_prev_tex;
uniform float u_alpha;
uniform int u_use_prev;
varying vec2 v_uv;
void main() {
    vec3 curr = texture2D(u_curr_tex, v_uv).rgb;
    vec3 outc = curr;
    if (u_use_prev == 1) {
        vec3 prev = texture2D(u_prev_tex, v_uv).rgb;
        outc = mix(prev, curr, clamp(u_alpha, 0.0, 1.0));
    }
    gl_FragColor = vec4(outc, 1.0);
}
"""


class GpuAnimatedBackground(QOpenGLWidget):
    """GPU metaballs + particles renderer with runtime shader compatibility fallback."""

    def __init__(self, parent=None):
        super().__init__(parent)

        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
        fmt.setDepthBufferSize(24)
        self.setFormat(fmt)
        self.setUpdateBehavior(QOpenGLWidget.NoPartialUpdate)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._effect_mode = "particles"
        self._metaballs = MetaballSimulation(count=10, seed=1337)
        self._particles = ParticleSimulation(count=112, seed=2024)
        self._program: QOpenGLShaderProgram | None = None
        self._blit_program: QOpenGLShaderProgram | None = None
        self._temporal_program: QOpenGLShaderProgram | None = None
        self._vao: QOpenGLVertexArrayObject | None = None
        self._vbo: QOpenGLBuffer | None = None
        self._offscreen_fbo: QOpenGLFramebufferObject | None = None
        self._history_fbo_a: QOpenGLFramebufferObject | None = None
        self._history_fbo_b: QOpenGLFramebufferObject | None = None
        self._history_valid = False
        self._history_index = 0
        self._temporal_alpha = 0.32
        self._offscreen_scale = 0.80
        self._offscreen_size = (0, 0)
        self._metaball_radius_boost = 1.8
        self._gpu_ready = False
        self._supports_known = False
        self._particles_supported = True
        self._metaballs_supported = True
        self._loc_res = -1
        self._loc_time = -1
        self._loc_mode = -1
        self._loc_metaball_count = -1
        self._loc_particle_count = -1
        self._loc_metaballs = -1
        self._loc_particles = -1
        self._loc_cam_pos = -1
        self._loc_cam_right = -1
        self._loc_cam_up = -1
        self._loc_cam_fwd = -1
        self._loc_cam_aspect = -1
        self._loc_cam_fov = -1
        self._loc_blit_tex = -1
        self._loc_temporal_curr = -1
        self._loc_temporal_prev = -1
        self._loc_temporal_alpha = -1
        self._loc_temporal_use_prev = -1
        self._start_ts = time.perf_counter()
        self._warned_metaball_uniform_missing = False
        self._warned_particle_uniform_missing = False
        self._logged_metaball_payload = False
        self._logged_particle_payload = False
        self._warned_metaballs_unsupported = False
        self._warned_particles_unsupported = False

        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._last_frame_ms = self._elapsed.elapsed()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_effect_mode(self, mode: str) -> None:
        normalized = (mode or "").strip().lower()
        if normalized == "metaballs":
            _log.info("Metaballs mode is currently disabled (TODO). Keeping particles mode.")
        # TODO(metaballs): Re-enable switching once metaballs mode is production-ready.
        # if normalized not in {"particles", "metaballs"}:
        #     normalized = "particles"
        # if normalized == "metaballs" and not self.supports_effect_mode("metaballs"):
        #     if not self._warned_metaballs_unsupported:
        #         _log.warning("Metaballs mode requested, but GPU shader uniforms are incomplete. Falling back to particles.")
        #         self._warned_metaballs_unsupported = True
        #     normalized = "particles"
        # if normalized == "particles" and not self.supports_effect_mode("particles") and self.supports_effect_mode("metaballs"):
        #     if not self._warned_particles_unsupported:
        #         _log.warning("Particles mode requested, but GPU shader uniforms are incomplete. Falling back to metaballs.")
        #         self._warned_particles_unsupported = True
        #     normalized = "metaballs"
        normalized = "particles"
        if normalized != self._effect_mode and normalized == "metaballs":
            self._reset_temporal_history()
        self._effect_mode = normalized
        self.update()

    @property
    def effect_mode(self) -> str:
        return self._effect_mode

    def supports_effect_mode(self, mode: str) -> bool:
        normalized = (mode or "").strip().lower()
        if normalized not in {"particles", "metaballs"}:
            normalized = "particles"
        if not self._supports_known:
            return True
        if normalized == "metaballs":
            return self._metaballs_supported
        return self._particles_supported

    def _tick(self) -> None:
        now = self._elapsed.elapsed()
        dt = max(0.0, min(1.0 / 30.0, (now - self._last_frame_ms) / 1000.0))
        self._last_frame_ms = now
        self._particles.step(dt)
        self._metaballs.step(dt)
        self.update()

    def _camera_basis(self, elapsed: float) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
        del elapsed
        yaw = 0.72
        pitch = 0.22
        dist = 2.30

        cp = math.cos(pitch)
        sp = math.sin(pitch)
        cy = math.cos(yaw)
        sy = math.sin(yaw)

        cam_x = dist * cp * sy
        cam_y = dist * sp
        cam_z = dist * cp * cy

        fx = -cam_x
        fy = -cam_y
        fz = -cam_z
        fl = math.sqrt(fx * fx + fy * fy + fz * fz) + 1e-8
        fx /= fl
        fy /= fl
        fz /= fl

        wx, wy, wz = 0.0, 1.0, 0.0
        rx = fy * wz - fz * wy
        ry = fz * wx - fx * wz
        rz = fx * wy - fy * wx
        rl = math.sqrt(rx * rx + ry * ry + rz * rz) + 1e-8
        rx /= rl
        ry /= rl
        rz /= rl

        ux = ry * fz - rz * fy
        uy = rz * fx - rx * fz
        uz = rx * fy - ry * fx
        ul = math.sqrt(ux * ux + uy * uy + uz * uz) + 1e-8
        ux /= ul
        uy /= ul
        uz /= ul

        return (cam_x, cam_y, cam_z), (rx, ry, rz), (ux, uy, uz), (fx, fy, fz)

    def _build_program(self) -> QOpenGLShaderProgram | None:
        for vs, fs, label in (
            (VERTEX_SHADER_330, FRAGMENT_SHADER_330, "GLSL330"),
            (VERTEX_SHADER_120, FRAGMENT_SHADER_120, "GLSL120"),
        ):
            prog = QOpenGLShaderProgram(self.context())
            prog.bindAttributeLocation("in_pos", 0)
            if not prog.addShaderFromSourceCode(QOpenGLShader.Vertex, vs):
                _log.warning("Background shader vertex compile failed (%s): %s", label, prog.log())
                continue
            if not prog.addShaderFromSourceCode(QOpenGLShader.Fragment, fs):
                _log.warning("Background shader fragment compile failed (%s): %s", label, prog.log())
                continue
            if not prog.link():
                _log.warning("Background shader link failed (%s): %s", label, prog.log())
                continue
            _log.info("Background renderer using %s", label)
            return prog
        return None

    def _build_blit_program(self) -> QOpenGLShaderProgram | None:
        for fs, label in (
            (BLIT_FRAGMENT_SHADER_330, "GLSL330"),
            (BLIT_FRAGMENT_SHADER_120, "GLSL120"),
        ):
            prog = QOpenGLShaderProgram(self.context())
            prog.bindAttributeLocation("in_pos", 0)
            if not prog.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX_SHADER_330 if label == "GLSL330" else VERTEX_SHADER_120):
                _log.warning("Background blit vertex compile failed (%s): %s", label, prog.log())
                continue
            if not prog.addShaderFromSourceCode(QOpenGLShader.Fragment, fs):
                _log.warning("Background blit fragment compile failed (%s): %s", label, prog.log())
                continue
            if not prog.link():
                _log.warning("Background blit link failed (%s): %s", label, prog.log())
                continue
            _log.info("Background blit program using %s", label)
            return prog
        return None

    def _build_temporal_program(self) -> QOpenGLShaderProgram | None:
        for fs, label in (
            (TEMPORAL_FRAGMENT_SHADER_330, "GLSL330"),
            (TEMPORAL_FRAGMENT_SHADER_120, "GLSL120"),
        ):
            prog = QOpenGLShaderProgram(self.context())
            prog.bindAttributeLocation("in_pos", 0)
            if not prog.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX_SHADER_330 if label == "GLSL330" else VERTEX_SHADER_120):
                _log.warning("Background temporal vertex compile failed (%s): %s", label, prog.log())
                continue
            if not prog.addShaderFromSourceCode(QOpenGLShader.Fragment, fs):
                _log.warning("Background temporal fragment compile failed (%s): %s", label, prog.log())
                continue
            if not prog.link():
                _log.warning("Background temporal link failed (%s): %s", label, prog.log())
                continue
            _log.info("Background temporal program using %s", label)
            return prog
        return None

    def _validate_uniform_layout(self) -> None:
        def missing(pairs: Sequence[tuple[str, int]]) -> list[str]:
            out: list[str] = []
            for name, loc in pairs:
                if loc < 0:
                    out.append(name)
            return out

        common_missing = missing(
            (
                ("u_res", self._loc_res),
                ("u_time", self._loc_time),
                ("u_mode", self._loc_mode),
            )
        )
        particle_missing = common_missing + missing(
            (
                ("u_particle_count", self._loc_particle_count),
                ("u_particles[0]", self._loc_particles),
            )
        )
        metaball_missing = common_missing + missing(
            (
                ("u_metaball_count", self._loc_metaball_count),
                ("u_metaballs[0]", self._loc_metaballs),
                ("u_cam_pos", self._loc_cam_pos),
                ("u_cam_right", self._loc_cam_right),
                ("u_cam_up", self._loc_cam_up),
                ("u_cam_fwd", self._loc_cam_fwd),
                ("u_cam_aspect", self._loc_cam_aspect),
                ("u_cam_fov", self._loc_cam_fov),
            )
        )

        self._supports_known = True
        self._particles_supported = len(particle_missing) == 0
        self._metaballs_supported = len(metaball_missing) == 0

        if not self._particles_supported:
            _log.error("Particles mode disabled: missing uniforms [%s].", ", ".join(particle_missing))
        if not self._metaballs_supported:
            _log.error("Metaballs mode disabled: missing uniforms [%s].", ", ".join(metaball_missing))
            self._reset_temporal_history()

        if self._effect_mode == "metaballs" and not self._metaballs_supported and self._particles_supported:
            self._effect_mode = "particles"
        elif self._effect_mode == "particles" and not self._particles_supported and self._metaballs_supported:
            self._effect_mode = "metaballs"
            self._reset_temporal_history()

        if not self._particles_supported and not self._metaballs_supported:
            self._gpu_ready = False
            _log.error("Background GPU renderer disabled: required shader uniforms are missing for both modes.")

    def _reset_temporal_history(self) -> None:
        self._history_valid = False
        self._history_index = 0

    def _release_offscreen_targets(self) -> None:
        self._offscreen_fbo = None
        self._history_fbo_a = None
        self._history_fbo_b = None
        self._offscreen_size = (0, 0)
        self._reset_temporal_history()

    def _history_fbos_ready(self) -> bool:
        return (
            self._history_fbo_a is not None
            and self._history_fbo_b is not None
            and self._history_fbo_a.isValid()
            and self._history_fbo_b.isValid()
        )

    def _ensure_offscreen_fbo(self, width: int, height: int) -> None:
        ow = max(1, int(width * self._offscreen_scale))
        oh = max(1, int(height * self._offscreen_scale))
        if (
            self._offscreen_fbo is not None
            and self._offscreen_size == (ow, oh)
            and self._offscreen_fbo.isValid()
            and self._history_fbos_ready()
        ):
            return

        self._release_offscreen_targets()
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setAttachment(QOpenGLFramebufferObject.NoAttachment)
        offscreen = QOpenGLFramebufferObject(ow, oh, fmt)
        history_a = QOpenGLFramebufferObject(ow, oh, fmt)
        history_b = QOpenGLFramebufferObject(ow, oh, fmt)
        if not offscreen.isValid() or not history_a.isValid() or not history_b.isValid():
            _log.warning("Background offscreen FBO creation failed for %sx%s.", ow, oh)
            return
        self._offscreen_fbo = offscreen
        self._history_fbo_a = history_a
        self._history_fbo_b = history_b
        self._offscreen_size = (ow, oh)
        self._reset_temporal_history()
        _log.info("Background offscreen/history FBO ready: %sx%s", ow, oh)

    def _prepare_render_state(self, funcs) -> None:
        funcs.glDisable(GL_DEPTH_TEST)
        funcs.glDisable(GL_CULL_FACE)
        funcs.glDisable(GL_SCISSOR_TEST)
        funcs.glDisable(GL_STENCIL_TEST)
        funcs.glDisable(GL_BLEND)
        funcs.glDepthMask(True)
        if hasattr(funcs, "glClearDepth"):
            funcs.glClearDepth(1.0)
        elif hasattr(funcs, "glClearDepthf"):
            funcs.glClearDepthf(1.0)

    def _draw_main_scene(
        self,
        funcs,
        width: int,
        height: int,
        elapsed: float,
        particle_payload: Sequence[float],
        particle_count: int,
        metaball_payload: Sequence[float],
        metaball_count: int,
    ) -> None:
        if self._program is None or self._vao is None:
            return
        cam, right, up, fwd = self._camera_basis(elapsed)
        aspect = float(width) / max(1.0, float(height))

        self._program.bind()
        if self._loc_res >= 0:
            self._program.setUniformValue(self._loc_res, float(width), float(height))
        if self._loc_time >= 0:
            self._program.setUniformValue(self._loc_time, elapsed)
        if self._loc_mode >= 0:
            self._program.setUniformValue(self._loc_mode, 1 if self._effect_mode == "metaballs" else 0)
        if self._loc_particle_count >= 0:
            self._program.setUniformValue(self._loc_particle_count, int(particle_count))
        if self._loc_metaball_count >= 0:
            self._program.setUniformValue(self._loc_metaball_count, int(metaball_count))
        if self._loc_cam_pos >= 0:
            self._program.setUniformValue(self._loc_cam_pos, cam[0], cam[1], cam[2])
        if self._loc_cam_right >= 0:
            self._program.setUniformValue(self._loc_cam_right, right[0], right[1], right[2])
        if self._loc_cam_up >= 0:
            self._program.setUniformValue(self._loc_cam_up, up[0], up[1], up[2])
        if self._loc_cam_fwd >= 0:
            self._program.setUniformValue(self._loc_cam_fwd, fwd[0], fwd[1], fwd[2])
        if self._loc_cam_aspect >= 0:
            self._program.setUniformValue(self._loc_cam_aspect, aspect)
        if self._loc_cam_fov >= 0:
            self._program.setUniformValue(self._loc_cam_fov, float(math.radians(54.0)))

        if particle_payload:
            if self._loc_particles >= 0:
                particle_buf = array("f", particle_payload)
                self._program.setUniformValueArray(self._loc_particles, particle_buf, particle_count, 4)
                if not self._logged_particle_payload and particle_count > 0:
                    _log.info("Particle upload sample: count=%s first=%s", particle_count, list(particle_buf[:4]))
                    self._logged_particle_payload = True
            elif not self._warned_particle_uniform_missing:
                _log.warning("Particle uniform location is -1; u_particles[0] not active.")
                self._warned_particle_uniform_missing = True
        if metaball_payload:
            if self._loc_metaballs >= 0:
                metaball_buf = array("f", metaball_payload)
                if abs(self._metaball_radius_boost - 1.0) > 1e-6:
                    for i in range(3, len(metaball_buf), 4):
                        metaball_buf[i] = float(metaball_buf[i] * self._metaball_radius_boost)
                self._program.setUniformValueArray(self._loc_metaballs, metaball_buf, metaball_count, 4)
                if not self._logged_metaball_payload and metaball_count > 0:
                    _log.info("Metaball upload sample: count=%s first=%s", metaball_count, list(metaball_buf[:4]))
                    self._logged_metaball_payload = True
            elif not self._warned_metaball_uniform_missing:
                _log.warning("Metaball uniform location is -1; u_metaballs[0] not active.")
                self._warned_metaball_uniform_missing = True

        self._vao.bind()
        funcs.glDrawArrays(GL_TRIANGLES, 0, 6)
        self._vao.release()
        self._program.release()

    def _draw_blit(self, funcs, texture_id: int) -> bool:
        if self._blit_program is None or self._vao is None:
            return False
        tex_id = int(texture_id)
        if tex_id <= 0:
            return False
        self._blit_program.bind()
        if self._loc_blit_tex >= 0:
            self._blit_program.setUniformValue(self._loc_blit_tex, 0)
        funcs.glActiveTexture(GL_TEXTURE0)
        funcs.glBindTexture(GL_TEXTURE_2D, tex_id)
        funcs.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        funcs.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        self._vao.bind()
        funcs.glDrawArrays(GL_TRIANGLES, 0, 6)
        self._vao.release()
        funcs.glBindTexture(GL_TEXTURE_2D, 0)
        self._blit_program.release()
        return True

    def _history_pair(self) -> tuple[QOpenGLFramebufferObject, QOpenGLFramebufferObject]:
        if not self._history_fbos_ready():
            raise RuntimeError("Temporal history FBOs are not ready")
        history = (self._history_fbo_a, self._history_fbo_b)
        return history[self._history_index], history[1 - self._history_index]

    def _draw_temporal_blend(self, funcs, current_tex_id: int, width: int, height: int) -> int:
        if self._temporal_program is None or self._vao is None or not self._history_fbos_ready():
            return current_tex_id
        if current_tex_id <= 0:
            return current_tex_id

        read_fbo, write_fbo = self._history_pair()
        write_fbo.bind()
        funcs.glViewport(0, 0, width, height)
        self._prepare_render_state(funcs)
        funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
        funcs.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        self._temporal_program.bind()
        if self._loc_temporal_curr >= 0:
            self._temporal_program.setUniformValue(self._loc_temporal_curr, 0)
        if self._loc_temporal_prev >= 0:
            self._temporal_program.setUniformValue(self._loc_temporal_prev, 1)
        if self._loc_temporal_alpha >= 0:
            self._temporal_program.setUniformValue(self._loc_temporal_alpha, float(self._temporal_alpha))
        if self._loc_temporal_use_prev >= 0:
            self._temporal_program.setUniformValue(self._loc_temporal_use_prev, 1 if self._history_valid else 0)

        prev_tex_id = int(read_fbo.texture())
        if (not self._history_valid) or prev_tex_id <= 0:
            prev_tex_id = current_tex_id

        funcs.glActiveTexture(GL_TEXTURE0)
        funcs.glBindTexture(GL_TEXTURE_2D, current_tex_id)
        funcs.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        funcs.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        funcs.glActiveTexture(GL_TEXTURE0 + 1)
        funcs.glBindTexture(GL_TEXTURE_2D, prev_tex_id)
        funcs.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        funcs.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        self._vao.bind()
        funcs.glDrawArrays(GL_TRIANGLES, 0, 6)
        self._vao.release()

        funcs.glActiveTexture(GL_TEXTURE0 + 1)
        funcs.glBindTexture(GL_TEXTURE_2D, 0)
        funcs.glActiveTexture(GL_TEXTURE0)
        funcs.glBindTexture(GL_TEXTURE_2D, 0)

        self._temporal_program.release()
        write_fbo.release()

        self._history_index = 1 - self._history_index
        self._history_valid = True
        active_history, _ = self._history_pair()
        history_tex = int(active_history.texture())
        return history_tex if history_tex > 0 else current_tex_id

    def initializeGL(self) -> None:
        self._program = self._build_program()
        if self._program is None:
            self._gpu_ready = False
            _log.error("Background GPU shader init failed. Rendering disabled.")
            return
        self._blit_program = self._build_blit_program()
        self._temporal_program = self._build_temporal_program()
        if self._blit_program is not None:
            self._blit_program.bind()
            self._loc_blit_tex = self._blit_program.uniformLocation("u_tex")
            self._blit_program.release()
        else:
            self._loc_blit_tex = -1
            _log.warning("Background blit program unavailable; metaballs will render full-res fallback.")
        if self._temporal_program is not None:
            self._temporal_program.bind()
            self._loc_temporal_curr = self._temporal_program.uniformLocation("u_curr_tex")
            self._loc_temporal_prev = self._temporal_program.uniformLocation("u_prev_tex")
            self._loc_temporal_alpha = self._temporal_program.uniformLocation("u_alpha")
            self._loc_temporal_use_prev = self._temporal_program.uniformLocation("u_use_prev")
            self._temporal_program.release()
        else:
            self._loc_temporal_curr = -1
            self._loc_temporal_prev = -1
            self._loc_temporal_alpha = -1
            self._loc_temporal_use_prev = -1
            _log.warning("Background temporal program unavailable; metaballs temporal stabilization disabled.")

        self._vao = QOpenGLVertexArrayObject(self)
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        if not self._vao.create() or not self._vbo.create():
            self._gpu_ready = False
            _log.error("Background GPU buffers init failed.")
            return

        quad = array("f", (-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0))

        self._vao.bind()
        self._vbo.bind()
        self._vbo.allocate(quad.tobytes(), len(quad) * 4)

        self._program.bind()
        self._program.enableAttributeArray(0)
        self._program.setAttributeBuffer(0, GL_FLOAT, 0, 2, 2 * 4)
        self._loc_res = self._program.uniformLocation("u_res")
        self._loc_time = self._program.uniformLocation("u_time")
        self._loc_mode = self._program.uniformLocation("u_mode")
        self._loc_metaball_count = self._program.uniformLocation("u_metaball_count")
        self._loc_particle_count = self._program.uniformLocation("u_particle_count")
        self._loc_metaballs = self._program.uniformLocation("u_metaballs[0]")
        self._loc_particles = self._program.uniformLocation("u_particles[0]")
        self._loc_cam_pos = self._program.uniformLocation("u_cam_pos")
        self._loc_cam_right = self._program.uniformLocation("u_cam_right")
        self._loc_cam_up = self._program.uniformLocation("u_cam_up")
        self._loc_cam_fwd = self._program.uniformLocation("u_cam_fwd")
        self._loc_cam_aspect = self._program.uniformLocation("u_cam_aspect")
        self._loc_cam_fov = self._program.uniformLocation("u_cam_fov")
        _log.info(
            "Background uniform locations: mode=%s metaball_count=%s metaballs=%s particles=%s",
            self._loc_mode,
            self._loc_metaball_count,
            self._loc_metaballs,
            self._loc_particles,
        )
        self._validate_uniform_layout()
        self._program.release()
        self._vbo.release()
        self._vao.release()

        if not self._particles_supported and not self._metaballs_supported:
            return

        self._gpu_ready = True
        dpr = max(1.0, float(self.devicePixelRatioF()))
        width = max(1, int(round(self.width() * dpr)))
        height = max(1, int(round(self.height() * dpr)))
        self._particles.resize(width, height)
        self._metaballs.resize(width, height)
        self._ensure_offscreen_fbo(width, height)

    def resizeGL(self, width: int, height: int) -> None:
        w = max(1, width)
        h = max(1, height)
        self._particles.resize(w, h)
        self._metaballs.resize(w, h)
        self._ensure_offscreen_fbo(w, h)
        self._reset_temporal_history()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        dpr = max(1.0, float(self.devicePixelRatioF()))
        w = max(1, int(round(self.width() * dpr)))
        h = max(1, int(round(self.height() * dpr)))
        self._particles.resize(w, h)
        self._metaballs.resize(w, h)
        self._ensure_offscreen_fbo(w, h)
        self._reset_temporal_history()

    def paintGL(self) -> None:
        funcs = QOpenGLContext.currentContext().functions()
        dpr = max(1.0, float(self.devicePixelRatioF()))
        width = max(1, int(round(self.width() * dpr)))
        height = max(1, int(round(self.height() * dpr)))
        funcs.glViewport(0, 0, width, height)
        self._prepare_render_state(funcs)

        if not self._gpu_ready or self._program is None or self._vao is None:
            funcs.glClearColor(8.0 / 255.0, 10.0 / 255.0, 16.0 / 255.0, 1.0)
            funcs.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            return

        if self._effect_mode == "metaballs" and not self.supports_effect_mode("metaballs"):
            if self.supports_effect_mode("particles"):
                if not self._warned_metaballs_unsupported:
                    _log.warning("Metaballs render skipped due missing uniforms. Switching to particles.")
                    self._warned_metaballs_unsupported = True
                self._effect_mode = "particles"
            else:
                funcs.glClearColor(8.0 / 255.0, 10.0 / 255.0, 16.0 / 255.0, 1.0)
                funcs.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                return
        if self._effect_mode == "particles" and not self.supports_effect_mode("particles"):
            if self.supports_effect_mode("metaballs"):
                if not self._warned_particles_unsupported:
                    _log.warning("Particles render skipped due missing uniforms. Switching to metaballs.")
                    self._warned_particles_unsupported = True
                self._effect_mode = "metaballs"
                self._reset_temporal_history()
            else:
                funcs.glClearColor(8.0 / 255.0, 10.0 / 255.0, 16.0 / 255.0, 1.0)
                funcs.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                return

        elapsed = float(time.perf_counter() - self._start_ts)

        if self._effect_mode == "particles":
            funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
            funcs.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            particle_payload = self._particles.shader_uniform_payload(max_count=MAX_PARTICLES)
            particle_count = len(particle_payload) // 4
            self._draw_main_scene(
                funcs,
                width,
                height,
                elapsed,
                particle_payload,
                particle_count,
                [],
                0,
            )
            return

        metaball_payload = self._metaballs.shader_uniform_payload(max_count=MAX_METABALLS)
        metaball_count = len(metaball_payload) // 4
        self._ensure_offscreen_fbo(width, height)
        if self._offscreen_fbo is not None and self._blit_program is not None and self._offscreen_fbo.isValid():
            ow, oh = self._offscreen_size
            self._offscreen_fbo.bind()
            funcs.glViewport(0, 0, ow, oh)
            self._prepare_render_state(funcs)
            funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
            funcs.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            self._draw_main_scene(
                funcs,
                ow,
                oh,
                elapsed,
                [],
                0,
                metaball_payload,
                metaball_count,
            )
            self._offscreen_fbo.release()

            source_tex = int(self._offscreen_fbo.texture())
            if source_tex > 0:
                source_tex = self._draw_temporal_blend(funcs, source_tex, ow, oh)

            funcs.glViewport(0, 0, width, height)
            self._prepare_render_state(funcs)
            funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
            funcs.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            if self._draw_blit(funcs, source_tex):
                return

        funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
        funcs.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._draw_main_scene(
            funcs,
            width,
            height,
            elapsed,
            [],
            0,
            metaball_payload,
            metaball_count,
        )
