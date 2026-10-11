#include <gtest/gtest.h>

#include "battlezone_simulation.h"
using namespace demo::battlezone;
TEST(Battlezone, DriveTurnAndFrameRate)
{
    Simulation a, b;
    a.obstacles = {};
    b.obstacles = {};
    for (int i = 0; i < 60; ++i)
        a.update(1.f / 60, {1, .5f});
    for (int i = 0; i < 30; ++i)
        b.update(1.f / 30, {1, .5f});
    EXPECT_NEAR(a.player.x, b.player.x, .001f);
    EXPECT_NEAR(a.player.z, b.player.z, .001f);
    EXPECT_GT(a.player.x, 1);
    EXPECT_LT(a.player.z, -5);
}
TEST(Battlezone, FireCooldownAndNearestObstacle)
{
    Simulation s;
    s.enemy = {0, -10};
    s.protection = 100;
    s.obstacles.push_back({
        {0, -6},
        2,
        false
    });
    s.update(1.f / 60, {0, 0, true});
    EXPECT_EQ(s.events.shots, 1);
    s.update(1.f / 60, {0, 0, true});
    EXPECT_EQ(s.events.shots, 0);
    for (int i = 0; i < 25; ++i)
        s.update(1.f / 60, {});
    EXPECT_EQ(s.score, 0);
    EXPECT_TRUE(s.projectiles.empty());
    EXPECT_LE(hit({0, 0}, {0, -20}, {0, -10}, 2), 1);
}
TEST(Battlezone, ScoreExactlyOnceAndEnemyRespawn)
{
    Simulation s;
    s.enemy = {0, -10};
    s.protection = 100;
    s.update(1.f / 60, {0, 0, true});
    for (int i = 0; i < 20; ++i)
        s.update(1.f / 60, {});
    EXPECT_EQ(s.score, 1000);
    EXPECT_GT(s.enemyDestroyed, 0);
    EXPECT_FALSE(s.fragments.empty());
    for (int i = 0; i < 80; ++i)
        s.update(1.f / 60, {});
    EXPECT_EQ(s.score, 1000);
    EXPECT_EQ(s.enemyDestroyed, 0);
    EXPECT_GT(distance(s.enemy, s.player), 20);
}
TEST(Battlezone, LivesProtectionRestartAndPause)
{
    Simulation s;
    for (int life = 0; life < 3; ++life)
    {
        s.protection = 0;
        s.playerDestroyed = 0;
        s.projectiles.push_back({
            s.player,
            {0, 0},
            true,
            1
        });
        s.update(1.f / 60, {});
        EXPECT_EQ(s.lives, 2 - life);
    }
    s.score = 4000;
    s.update(.02f, {0, 0, false, true});
    EXPECT_EQ(s.lives, 3);
    EXPECT_EQ(s.score, 0);
    EXPECT_TRUE(s.projectiles.empty());
    s.update(.001f, {0, 0, true});
    s.pause();
    s.update(.02f, {});
    EXPECT_TRUE(s.projectiles.empty());
    s.update(50, {1, 0});
    EXPECT_LT(distance(s.player, {}), 2);
}
TEST(Battlezone, TankCannotCrossObstacle)
{
    Simulation s;
    s.obstacles.push_back({
        {0, -5},
        2,
        false
    });
    for (int i = 0; i < 60; ++i)
        s.update(1.f / 60, {1, 0});
    EXPECT_GT(s.player.z, -1.1f);
}
