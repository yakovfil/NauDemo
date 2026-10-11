// Copyright 2024 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.

#include "nau/module/module.h"

#include "free_camera.h"
#include "battlezone.h"
#include "click_feedback.h"
#include "mover.h"
#include "myapi_impl.h"
#include "rotator.h"

class MainGameModule final : public nau::DefaultModuleImpl
{
    std::string getModuleName() override
    {
        return "MainGameModule";
    }

    void initialize() override
    {
        NAU_MODULE_EXPORT_SERVICE(MyApiImpl);
        nau::getServiceProvider().addClass<MyRotator>();
        nau::getServiceProvider().addClass<MyMover>();
        nau::getServiceProvider().addClass<DemoBattlezone>();
#ifdef NAU_DEMO_PORTABLE_INPUT
        nau::getServiceProvider().addClass<DemoFreeCamera>();
#endif
#ifdef NAU_DEMO_PORTABLE_AUDIO
        nau::getServiceProvider().addClass<DemoClickFeedback>();
#endif
    }
};

IMPLEMENT_MODULE(MainGameModule)
