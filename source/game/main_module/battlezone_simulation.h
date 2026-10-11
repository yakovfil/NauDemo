// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace demo::battlezone
{
    inline constexpr float TankRadius = 3.7f;
    struct Point
    {
        float x = 0, z = 0;
    };
    inline Point operator+(Point a, Point b)
    {
        return {a.x + b.x, a.z + b.z};
    }
    inline Point operator-(Point a, Point b)
    {
        return {a.x - b.x, a.z - b.z};
    }
    inline Point operator*(Point a, float f)
    {
        return {a.x * f, a.z * f};
    }
    inline float dot(Point a, Point b)
    {
        return a.x * b.x + a.z * b.z;
    }
    inline float distance(Point a, Point b)
    {
        return std::hypot(a.x - b.x, a.z - b.z);
    }
    inline Point direction(float heading)
    {
        return {std::sin(heading), -std::cos(heading)};
    }
    struct Obstacle
    {
        Point position;
        float radius = 3;
        bool pyramid = false;
    };
    struct Projectile
    {
        Point position, velocity;
        bool enemy = false;
        float life = 3;
    };
    struct Fragment
    {
        Point position, velocity;
        float height = 0, rise = 0, life = 1;
    };
    struct Controls
    {
        float drive = 0, turn = 0;
        bool fire = false, restart = false;
    };
    struct Events
    {
        unsigned shots = 0, explosions = 0;
    };
    // Segment-circle intersection returns the earliest hit, including an initial overlap.
    inline float hit(Point a, Point b, Point center, float radius)
    {
        const auto v = b - a, offset = a - center;
        const float c = dot(offset, offset) - radius * radius;
        if (c <= 0)
            return 0;
        const float aa = dot(v, v), bb = dot(offset, v);
        const float discriminant = bb * bb - aa * c;
        if (aa <= 1e-9f || discriminant < 0)
            return 2;
        const float t = (-bb - std::sqrt(discriminant)) / aa;
        return t >= 0 && t <= 1 ? t : 2;
    }
    class Simulation
    {
    public:
        std::vector<Obstacle> obstacles;
        Point player{}, enemy{0, -38};
        float heading = 0, enemyHeading = 3.14159265f;
        unsigned score = 0, lives = 3;
        float protection = 2, playerDestroyed = 0, enemyDestroyed = 0;
        std::vector<Projectile> projectiles;
        std::vector<Fragment> fragments;
        Events events;
        void reset()
        {
            player = {};
            enemy = {0, -38};
            heading = 0;
            enemyHeading = 3.14159265f;
            score = 0;
            lives = 3;
            protection = 2;
            playerDestroyed = enemyDestroyed = 0;
            m_fire = 0;
            m_enemyFire = 2;
            m_accumulator = 0;
            m_firePending = false;
            projectiles.clear();
            fragments.clear();
            events = {};
            m_seed = 12345;
        }
        void pause()
        {
            m_accumulator = 0;
            m_firePending = false;
            events = {};
        }
        void update(float dt, Controls controls)
        {
            events = {};
            if (controls.restart && !lives)
            {
                reset();
                return;
            }
            if (!lives)
                return;
            m_firePending |= controls.fire;
            m_accumulator += std::clamp(dt, 0.f, 5.f / 60);
            for (unsigned i = 0; i < 5 && m_accumulator + 1e-7f >= 1.f / 60; ++i)
            {
                controls.fire = m_firePending;
                m_firePending = false;
                step(1.f / 60, controls);
                m_accumulator -= 1.f / 60;
                if (!lives)
                {
                    m_accumulator = 0;
                    m_firePending = false;
                    break;
                }
            }
        }

    private:
        float m_fire = 0, m_enemyFire = 2, m_accumulator = 0;
        bool m_firePending = false;
        unsigned m_seed = 12345;
        float random()
        {
            m_seed = m_seed * 1664525 + 1013904223;
            return float(m_seed >> 8) / 16777216;
        }
        bool free(Point p, float radius) const
        {
            if (std::abs(p.x) > 95 || std::abs(p.z) > 95)
                return false;
            for (const auto& obstacle : obstacles)
                if (distance(p, obstacle.position) < radius + obstacle.radius)
                    return false;
            return true;
        }
        void move(Point& position, Point displacement)
        {
            const auto target = position + displacement;
            bool blocked = !free(target, TankRadius);
            for (const auto& obstacle : obstacles)
                blocked |= hit(position, target, obstacle.position, obstacle.radius + TankRadius) <= 1;
            if (!blocked)
                position = target;
        }
        void shoot(Point origin, float angle, bool hostile)
        {
            if (projectiles.size() == 32)
                projectiles.erase(projectiles.begin());
            projectiles.push_back({origin + direction(angle) * (TankRadius + .1f), direction(angle) * 55.f, hostile, 3});
            ++events.shots;
        }
        void explode(Point origin)
        {
            ++events.explosions;
            for (unsigned i = 0; i < 20; ++i)
            {
                if (fragments.size() == 128)
                    fragments.erase(fragments.begin());
                fragments.push_back({origin, direction(random() * 6.283185f) * (3 + random() * 8), 1, 3 + random() * 5, 1});
            }
        }
        void spawn()
        {
            for (unsigned i = 0; i < 32; ++i)
            {
                const Point p = player + direction(heading + (random() - .5f) * 2) * 38.f;
                if (free(p, TankRadius) && distance(p, player) > 20)
                {
                    enemy = p;
                    return;
                }
            }
            for (int x = -80; x <= 80; x += 20)
                for (int z = -80; z <= 80; z += 20)
                    if (free({float(x), float(z)}, TankRadius) && distance({float(x), float(z)}, player) > 20)
                    {
                        enemy = {float(x), float(z)};
                        return;
                    }
        }
        void step(float dt, Controls c)
        {
            protection = std::max(0.f, protection - dt);
            m_fire = std::max(0.f, m_fire - dt);
            m_enemyFire -= dt;
            if (playerDestroyed > 0)
            {
                playerDestroyed = std::max(0.f, playerDestroyed - dt);
                if (playerDestroyed == 0)
                {
                    player = {};
                    heading = 0;
                    protection = 2;
                    projectiles.clear();
                }
            }
            else
            {
                heading = std::remainder(heading + c.turn * dt * 1.3f, 6.2831853f);
                move(player, direction(heading) * (c.drive * dt * 12));
                if (c.fire && m_fire == 0)
                {
                    shoot(player, heading, false);
                    m_fire = .35f;
                }
            }
            if (enemyDestroyed > 0)
            {
                enemyDestroyed = std::max(0.f, enemyDestroyed - dt);
                if (enemyDestroyed == 0)
                {
                    spawn();
                    m_enemyFire = 2;
                }
            }
            else
            {
                const auto delta = player - enemy;
                const float target = std::atan2(delta.x, -delta.z);
                const float error = std::remainder(target - enemyHeading, 6.2831853f);
                enemyHeading += std::clamp(error, -dt * .6f, dt * .6f);
                if (distance(player, enemy) > 24)
                    move(enemy, direction(enemyHeading) * (dt * 3));
                if (std::abs(error) < .08f && m_enemyFire <= 0 && protection == 0 && playerDestroyed == 0)
                {
                    shoot(enemy, enemyHeading, true);
                    m_enemyFire = 2.5f;
                }
            }
            for (auto it = projectiles.begin(); it != projectiles.end();)
            {
                const auto end = it->position + it->velocity * dt;
                float obstacleHit = 2;
                for (const auto& obstacle : obstacles)
                    obstacleHit = std::min(obstacleHit, hit(it->position, end, obstacle.position, obstacle.radius));
                const bool targetAlive = it->enemy ? lives && playerDestroyed == 0 && protection == 0 : enemyDestroyed == 0;
                const float targetHit = targetAlive ? hit(it->position, end, it->enemy ? player : enemy, TankRadius) : 2;
                if (targetHit < obstacleHit && targetHit <= 1)
                {
                    if (it->enemy)
                    {
                        --lives;
                        playerDestroyed = 1;
                        explode(player);
                    }
                    else
                    {
                        score += 1000;
                        enemyDestroyed = 1;
                        explode(enemy);
                    }
                }
                it->life -= dt;
                if (std::min(targetHit, obstacleHit) <= 1 || it->life <= 0 || !free(end, 0))
                    it = projectiles.erase(it);
                else
                {
                    it->position = end;
                    ++it;
                }
            }
            for (auto& fragment : fragments)
            {
                fragment.position = fragment.position + fragment.velocity * dt;
                fragment.height += fragment.rise * dt;
                fragment.rise -= dt * 12;
                fragment.life -= dt;
            }
            std::erase_if(fragments, [](const auto& f)
            {
                return f.life <= 0;
            });
        }
    };
}  // namespace demo::battlezone
