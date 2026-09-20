#version 300 es
precision highp float;
in vec3 worldNormal;
out vec4 color;
void main() {
    float diffuse = max(dot(normalize(worldNormal), normalize(vec3(-0.5, 0.8, 0.6))), 0.0);
    color = vec4(vec3(0.06, 0.32, 0.95) * (0.25 + 0.75 * diffuse), 1.0);
}
