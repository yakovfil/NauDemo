// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#pragma once
#ifdef NAU_DEMO_PORTABLE_INPUT
    #include "nau/app/main_loop/game_system.h"
    #include "nau/rtti/rtti_impl.h"

class DemoFreeCamera final : public nau::IGamePreUpdate,
                             public nau::IRttiObject
{
    NAU_RTTI_CLASS(DemoFreeCamera, nau::IGamePreUpdate, nau::IRttiObject)
    void gamePreUpdate(std::chrono::milliseconds dt) override;
};
#endif
