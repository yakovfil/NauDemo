// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#include "battlezone.h"
#ifndef NAU_DEMO_PORTABLE_VECTORS
NAU_IMPLEMENT_DYNAMIC_OBJECT(DemoBattlezone)
#endif
#ifdef NAU_DEMO_PORTABLE_VECTORS
    #include <limits>

    #include "nau/app/application.h"
    #include "nau/input.h"
    #include "nau/io/virtual_file_system.h"
    #include "nau/scene/camera/camera_manager.h"
    #include "nau/scene/components/camera_component.h"
    #include "nau/scene/internal/scene_manager_internal.h"
    #include "nau/scene/scene_object.h"
    #include "nau/serialization/json.h"
    #include "nau_project_policy.h"

NAU_IMPLEMENT_DYNAMIC_OBJECT(DemoBattlezone)

namespace
{
    using namespace nau;
    RuntimeValue::Ptr field(RuntimeValue::Ptr v, std::string_view key)
    {
        auto* object = v ? v->as<RuntimeReadonlyDictionary*>() : nullptr;
        return object ? object->getValue(key) : nullptr;
    }
    float number(RuntimeValue::Ptr v)
    {
        if (v)
        {
            if (auto* f = v->as<RuntimeFloatValue*>())
                return f->getSingle();
            if (auto* i = v->as<RuntimeIntegerValue*>())
                return i->isSigned() ? float(i->getInt64()) : float(i->getUint64());
        }
        return std::numeric_limits<float>::quiet_NaN();
    }
    RuntimeReadonlyCollection* list(RuntimeValue::Ptr v)
    {
        return v ? v->as<RuntimeReadonlyCollection*>() : nullptr;
    }
    Result<RuntimeValue::Ptr> readData(const std::string& path)
    {
        if (!path.starts_with("/content/") || !path.ends_with(".json") || path.find("..") != std::string::npos || path.find('\\') != std::string::npos)
            return NauMakeError("Invalid packaged game path {}", path);
        auto file = getServiceProvider().get<io::IVirtualFileSystem>().openFile(path, io::AccessMode::Read, io::OpenFileMode::OpenExisting);
        io::IStreamReader::Ptr stream = file ? file->createStream() : nullptr;
        if (!stream || !file->getSize() || file->getSize() > 1024 * 1024)
            return NauMakeError("Missing or oversized game data {}", path);
        return serialization::jsonParse(*stream);
    }
}  // namespace

nau::async::Task<> DemoBattlezone::activateComponentAsync()
{
    using namespace nau;
    auto parsed = readData(m_content);
    if (!parsed)
        co_await async::Task<>::makeRejected(parsed.getError());
    auto geometry = field(*parsed, "geometry"), obstacles = field(*parsed, "obstacles");
    auto* document = *parsed ? (*parsed)->as<RuntimeReadonlyDictionary*>() : nullptr;
    auto* shapes = geometry ? geometry->as<RuntimeReadonlyDictionary*>() : nullptr;
    auto* layout = list(obstacles);
    if (!document || document->getSize() != 3 || number(field(*parsed, "version")) != 1 || !shapes || !layout || shapes->getSize() > 64 || layout->getSize() > 128)
        co_await async::Task<>::makeRejected(NauMakeError("Invalid game data {}", m_content));
    for (size_t i = 0; i < shapes->getSize(); ++i)
    {
        std::string name{shapes->getKey(i)};
        auto value = shapes->getValue(name), vertices = field(value, "vertices"), edges = field(value, "edges");
        auto* shapeFields = value ? value->as<RuntimeReadonlyDictionary*>() : nullptr;
        auto* v = list(vertices);
        auto* e = list(edges);
        if (!shapeFields || shapeFields->getSize() != 2 || !v || !e || v->getSize() > 4096 || !v->getSize() || e->getSize() > 16384 || !e->getSize())
            co_await async::Task<>::makeRejected(NauMakeError("Invalid game geometry {}:{}", m_content, name));
        Shape shape;
        for (size_t j = 0; j < v->getSize(); ++j)
        {
            auto item = v->getAt(j);
            auto* xyz = list(item);
            if (!xyz || xyz->getSize() != 3)
                co_await async::Task<>::makeRejected(NauMakeError("Invalid game vertex {}:{}", m_content, name));
            std::array<float, 3> point;
            for (unsigned axis = 0; axis < 3; ++axis)
            {
                point[axis] = number(xyz->getAt(axis));
                if (!std::isfinite(point[axis]) || std::abs(point[axis]) > 10000)
                    co_await async::Task<>::makeRejected(NauMakeError("Invalid game vertex coordinate {}:{}", m_content, name));
            }
            shape.vertices.push_back(point);
        }
        for (size_t j = 0; j < e->getSize(); ++j)
        {
            auto item = e->getAt(j);
            auto* pair = list(item);
            if (!pair || pair->getSize() != 2)
                co_await async::Task<>::makeRejected(NauMakeError("Invalid game edge {}:{}", m_content, name));
            std::array<unsigned, 2> indices;
            for (unsigned k = 0; k < 2; ++k)
            {
                float n = number(pair->getAt(k));
                if (!std::isfinite(n) || n < 0 || n >= shape.vertices.size() || n != std::floor(n))
                    co_await async::Task<>::makeRejected(NauMakeError("Invalid game edge index {}:{}", m_content, name));
                indices[k] = unsigned(n);
            }
            shape.edges.push_back(indices);
        }
        m_shapes.emplace(name, std::move(shape));
    }
    for (auto name : {"tank", "box", "pyramid", "radar", "projectile", "chunk0", "chunk1", "chunk2",
                      "tread0", "tread1", "tread2", "tread3", "tread4", "tread5", "tread6", "tread7"})
        if (!m_shapes.contains(name))
            co_await async::Task<>::makeRejected(NauMakeError("Missing game shape {}:{}", m_content, name));
    for (char c : std::string_view{"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-"})
        if (!m_shapes.contains(std::string{"glyph_"} + c))
            co_await async::Task<>::makeRejected(NauMakeError("Missing game glyph {}:{}", m_content, c));
    for (size_t i = 0; i < layout->getSize(); ++i)
    {
        auto item = layout->getAt(i);
        auto* obstacleFields = item ? item->as<RuntimeReadonlyDictionary*>() : nullptr;
        const float x = number(field(item, "x")), z = number(field(item, "z")), radius = number(field(item, "radius")), pyramid = number(field(item, "pyramid"));
        if (!obstacleFields || obstacleFields->getSize() != 4 || !std::isfinite(x) || !std::isfinite(z) || std::abs(x) > 90 || std::abs(z) > 90 || !std::isfinite(radius) || radius < 1 || radius > 8 || (pyramid != 0 && pyramid != 1) || std::hypot(x, z) < radius + 4 || std::hypot(x, z + 38) < radius + 4)
            co_await async::Task<>::makeRejected(NauMakeError("Invalid game obstacle {}", m_content));
        m_game.obstacles.push_back({
            {x, z},
            radius,
            pyramid != 0
        });
    }
    auto& audio = getServiceProvider().get<audio::IPortableAudio>();
    auto fire = audio.loadClip(nau::project::Sound_fire), explosion = audio.loadClip(nau::project::Sound_explosion);
    if (!fire)
        co_await async::Task<>::makeRejected(fire.getError());
    if (!explosion)
        co_await async::Task<>::makeRejected(explosion.getError());
    m_fire = *fire;
    m_explosion = *explosion;
    m_epoch = input::inputResetGeneration();
    m_active = true;
    NAU_LOG_INFO("Battlezone content ready: {}", m_content);
}
void DemoBattlezone::deactivateComponent()
{
    m_active = false;
    m_game.pause();
    m_shapes.clear();
    m_fire.reset();
    m_explosion.reset();
    if (auto* audio = nau::getServiceProvider().find<nau::audio::IPortableAudio>())
        audio->cancelPending();
}
void DemoBattlezone::updateComponent(float dt)
{
    using namespace nau;
    using namespace input;
    if (!m_active || getApplication().isClosing())
        return;
    auto& audio = getServiceProvider().get<audio::IPortableAudio>();
    const auto epoch = inputResetGeneration();
    if (epoch != m_epoch)
    {
        m_epoch = epoch;
        m_game.pause();
        audio.cancelPending();
    }
    if (!isKeyboardButtonHold(0, Key::Focus) || epoch != inputFrameResetGeneration())
    {
        m_game.pause();
        audio.cancelPending();
        return;
    }
    demo::battlezone::Controls controls;
    controls.drive = float(isKeyboardButtonHold(0, Key::W)) - float(isKeyboardButtonHold(0, Key::S));
    controls.turn = float(isKeyboardButtonHold(0, Key::D)) - float(isKeyboardButtonHold(0, Key::A));
    controls.fire = keyboardPressCount(0, Key::Space) || mousePressCount(0, MouseKey::ButtonLeft);
    controls.restart = keyboardPressCount(0, Key::R) != 0;
    const auto previousEnemy = m_game.enemy;
    m_game.update(dt, controls);
    if (m_game.lives && std::isfinite(dt))
    {
        m_artTime = std::fmod(m_artTime + std::clamp(dt, 0.f, .0833333f), 1000.f);
        m_treadPhase = std::fmod(m_treadPhase + demo::battlezone::distance(previousEnemy, m_game.enemy) * 4.f, 4.f);
    }
    if (epoch != inputResetGeneration() || getApplication().isClosing())
    {
        m_game.pause();
        audio.cancelPending();
        return;
    }
    if (controls.restart)
    {
        discardPendingPresses();
        audio.cancelPending();
    }
    auto camera = getServiceProvider().get<scene::ICameraManager>().getCameras().getWorldMainCamera();
    auto* component = camera ? getServiceProvider().get<scene::ISceneManagerInternal>().findComponent(camera->getCameraUid()) : nullptr;
    auto* actual = component ? component->as<scene::CameraComponent*>() : nullptr;
    if (actual)
    {
        math::Transform transform{math::Quat::rotationY(-m_game.heading), math::Vector3(m_game.player.x, 2.4f - m_game.playerDestroyed * .25f, m_game.player.z)};
        actual->setWorldTransform(getParentObject().getWorldTransform() * transform);
    }
    if (audio.outputState() == audio::OutputState::Failed)
    {
        NAU_LOG_ERROR("Battlezone audio device failed");
        getApplication().stop();
        return;
    }
    for (unsigned i = 0; i < m_game.events.shots + m_game.events.explosions; ++i)
    {
        auto played = audio.play(i < m_game.events.shots ? m_fire : m_explosion);
        if (!played)
        {
            NAU_LOG_ERROR("Battlezone effect failed: {}", played.getError()->getDiagMessage());
            getApplication().stop();
            break;
        }
    }
}
nau::Result<nau::render::VectorPresentation> DemoBattlezone::vectorPresentation() const
{
    using namespace nau::render;
    VectorPresentation p;
    p.owner = "Battlezone:" + nau::toString(getUid());
    p.blackBackground = true;
    if (!m_active)
        return p;
    const auto shape = [&](const std::string& name, demo::battlezone::Point location, float heading, float scale, float height = 0.f)
    {
        const auto& data = m_shapes.at(name);
        const auto point = [&](unsigned index)
        {
            auto v = data.vertices[index];
            return std::array<float, 3>{location.x + scale * (v[0] * std::cos(heading) - v[2] * std::sin(heading)), height + v[1] * scale, location.z + scale * (v[0] * std::sin(heading) + v[2] * std::cos(heading))};
        };
        for (auto edge : data.edges)
            p.world.push_back({point(edge[0]), point(edge[1])});
    };
    for (const auto& obstacle : m_game.obstacles)
    {
        const std::string name = obstacle.pyramid ? "pyramid" : "box";
        float radius = 0;
        for (const auto& vertex : m_shapes.at(name).vertices)
            radius = std::max(radius, std::hypot(vertex[0], vertex[2]));
        if (radius <= 1e-6f)
            return NauMakeError("Invalid planar obstacle shape {}", name);
        shape(name, obstacle.position, 0, obstacle.radius / radius);
    }
    if (m_game.enemyDestroyed == 0)
    {
        shape("tank", m_game.enemy, -m_game.enemyHeading, 1);
        const auto facing = demo::battlezone::direction(m_game.enemyHeading);
        const bool front = demo::battlezone::dot(m_game.player - m_game.enemy, facing) >= 0;
        shape("tread" + std::to_string((front ? 4 : 0) + unsigned(m_treadPhase)), m_game.enemy, -m_game.enemyHeading, 1);
        const auto mount = m_game.enemy + facing * -1.28f;
        shape("radar", mount, -m_game.enemyHeading + m_artTime * 2.f, 1);
    }
    for (const auto& shot : m_game.projectiles)
        shape("projectile", shot.position, -std::atan2(shot.velocity.x, -shot.velocity.z), 1, 1.04f);
    unsigned chunk = 0;
    for (const auto& fragment : m_game.fragments)
        shape("chunk" + std::to_string(chunk++ % 3), fragment.position, fragment.life * 6.f, .5f, fragment.height);
    const auto text = [&](VectorPresentation& output, const std::string& value, float x, float y, float size)
    {
        for (char c : value)
        {
            if (c != ' ')
            {
                const auto& glyph = m_shapes.at(std::string{"glyph_"} + c);
                for (const auto& edge : glyph.edges)
                {
                    const auto& a = glyph.vertices[edge[0]];
                    const auto& b = glyph.vertices[edge[1]];
                    output.overlay.push_back({
                        {x + a[0] * size, y + a[1] * size, 0},
                        {x + b[0] * size, y + b[1] * size, 0}
                    });
                }
            }
            x += size * 1.5f;
        }
    };
    // Wrapped panorama is heading-relative and deliberately dimmer than the battlefield.
    const float offset = m_game.heading * 400 / 3.14159265f;
    for (int i = -16; i <= 16; ++i)
    {
        float x = i * 70.f - offset;
        x = std::remainder(x, 1600.f) + 400;
        const float top = 245 - std::abs(i % 4) * 15.f;
        p.background.push_back({
            {     x,  280, 0},
            {x + 35,  top, 0},
            {     0, .45f, 0}
        });
        p.background.push_back({
            {x + 35,  top, 0},
            {x + 70,  280, 0},
            {     0, .45f, 0}
        });
    }
    const auto panorama = [&](float base)
    {
        return std::remainder(base - offset - 400, 1600.f) + 400;
    };
    float volcano = panorama(100);
    for (auto l : std::vector<VectorLine>{
             {{volcano - 60, 280, 0}, {volcano - 15, 205, 0}},
             {{volcano - 15, 205, 0}, {volcano + 15, 205, 0}},
             {{volcano + 15, 205, 0}, {volcano + 60, 280, 0}},
             {     {volcano, 205, 0},  {volcano - 7, 185, 0}},
             { {volcano - 7, 185, 0}, {volcano + 10, 172, 0}}
    })
    {
        l.color = {0, .55f, 0};
        p.background.push_back(l);
    }
    const float moon = panorama(600);
    for (int i = 0; i < 24; ++i)
    {
        float a = i * 6.283185f / 24, b = (i + 1) * 6.283185f / 24;
        p.background.push_back({
            {moon + 14 * std::cos(a), 180 + 14 * std::sin(a), 0},
            {moon + 14 * std::cos(b), 180 + 14 * std::sin(b), 0},
            {                      0,                   .65f, 0}
        });
    }
    p.background.push_back({
        {  0, 280, 0},
        {800, 280, 0},
        {  0, .3f, 0}
    });
    for (auto line : std::vector<VectorLine>{
             {{370, 300, 0}, {390, 300, 0}},
             {{410, 300, 0}, {430, 300, 0}},
             {{400, 275, 0}, {400, 290, 0}},
             {{400, 310, 0}, {400, 325, 0}}
    })
        p.overlay.push_back(line);
    text(p, "SCORE " + std::to_string(m_game.score), 30, 25, 12);
    text(p, "LIVES " + std::to_string(m_game.lives), 610, 25, 12);
    text(p, "W S DRIVE  A D TURN", 35, 548, 9);
    text(p, "SPACE OR CLICK FIRE", 35, 572, 9);
    for (int i = 0; i < 32; ++i)
    {
        float a = i * 6.283185f / 32, b = (i + 1) * 6.283185f / 32;
        p.overlay.push_back({
            {400 + 45 * std::cos(a), 80 + 45 * std::sin(a), 0},
            {400 + 45 * std::cos(b), 80 + 45 * std::sin(b), 0}
        });
    }
    p.overlay.push_back({
        {400, 80, 0},
        {375, 42, 0}
    });
    p.overlay.push_back({
        {400, 80, 0},
        {425, 42, 0}
    });
    if (m_game.enemyDestroyed == 0)
    {
        auto delta = m_game.enemy - m_game.player;
        float bearing = std::atan2(delta.x, -delta.z) - m_game.heading;
        float r = std::min(40.f, demo::battlezone::distance(m_game.enemy, m_game.player) * .8f);
        float x = 400 + std::sin(bearing) * r, y = 80 - std::cos(bearing) * r;
        p.overlay.push_back({
            {x - 2, y,   0},
            {x + 2, y,   0},
            {  .1f, 1, .1f},
            4
        });
    }
    if (!m_game.lives)
    {
        text(p, "GAME OVER", 290, 390, 20);
        text(p, "R TO RESTART", 285, 435, 14);
    }
    else if (m_game.playerDestroyed > 0)
        text(p, "TANK DESTROYED", 260, 410, 15);
    const auto& model = getParentObject().getWorldTransform();
    if (!model.isValid())
        return NauMakeError("Invalid Battlezone scene transform");
    for (auto& line : p.world)
        for (auto* point : {&line.a, &line.b})
        {
            const auto transformed = model.transformPoint(nau::math::Point3((*point)[0], (*point)[1], (*point)[2]));
            *point = {float(transformed.getX()), float(transformed.getY()), float(transformed.getZ())};
        }
    return p;
}
#endif
