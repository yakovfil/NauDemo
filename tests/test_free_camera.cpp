// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#include <gtest/gtest.h>

#include "free_camera_motion.h"

TEST(FreeCamera, NoInputPreservesTransform)
{
    nau::math::Transform transform{nau::math::Quat::rotationY(.5f), nau::math::Vector3(2, 3, 4)};
    EXPECT_FALSE(demo::moveCamera(transform, {}, .016f));
    EXPECT_FLOAT_EQ(float(transform.getTranslation().getX()), 2);
    EXPECT_FLOAT_EQ(float(transform.getRotation().getY()), float(nau::math::Quat::rotationY(.5f).getY()));
}

TEST(FreeCamera, DirectionsDiagonalAndElapsedBound)
{
    using namespace nau::math;
    Transform forward, diagonal, suspended, vertical;
    demo::CameraInput input;
    input.forward = 1;
    demo::moveCamera(forward, input, .02f);
    EXPECT_NEAR(float(forward.getTranslation().getZ()), -.06f, .0001f);
    input.right = 1;
    demo::moveCamera(diagonal, input, .02f);
    EXPECT_NEAR(float(length(diagonal.getTranslation())), .06f, .0001f);
    demo::moveCamera(suspended, input, 300.f);
    EXPECT_NEAR(float(length(suspended.getTranslation())), .15f, .0001f);
    input = {};
    input.vertical = 1;
    demo::moveCamera(vertical, input, .02f);
    EXPECT_NEAR(float(vertical.getTranslation().getY()), .06f, .0001f);
    Transform facing{Quat::rotationY(1.5707963f)};
    input = {};
    input.forward = 1;
    demo::moveCamera(facing, input, .02f);
    EXPECT_NEAR(float(facing.getTranslation().getX()), -.06f, .0001f);
}

TEST(FreeCamera, DragOnlyAndClampedPitch)
{
    using namespace nau::math;
    Transform transform;
    demo::CameraInput input;
    input.dx = 50;
    input.dy = -10000;
    EXPECT_FALSE(demo::moveCamera(transform, input, .016f));
    input.drag = true;
    EXPECT_TRUE(demo::moveCamera(transform, input, .016f));
    const auto forward = rotate(transform.getRotation(), Vector3(0, 0, -1));
    EXPECT_GT(float(forward.getY()), .99f);
    EXPECT_LT(float(forward.getY()), 1.f);
    EXPECT_TRUE(transform.isValid());
    input = {};
    EXPECT_FALSE(demo::moveCamera(transform, input, .016f));
}
