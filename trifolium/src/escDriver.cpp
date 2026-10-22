#include "escDriver.h"

EscDriver::EscDriver(uint8_t escPin, uint16_t dshotRate, bool forwardOnly)
{
    isForward = true;
    forwardOnly_ = forwardOnly;
    esc = new BidirDShotX1(escPin, dshotRate);
    throttleValue = DSHOT_CMD_MOTOR_STOP;
}

// Forward-only runs at dutyCycle and ignores reverseDirection; the alternating mode ignores both.
void EscDriver::drive(float dutyCycle, bool reverseDirection)
{
    if (forwardOnly_)
    {
        // Any throttle at all, since 0 is the motor-stop command.
        throttleValue = (uint16_t)constrain(lroundf(dutyCycle * 2000.0f), 1L, 2000L);
    }
    else if (isForward == true)
    {
        throttleValue = 2000;
        isForward = false;
    }
    else
    {
        throttleValue = 1000;
        isForward = true;
    }
    update();
}

void EscDriver::coast()
{
    throttleValue = DSHOT_CMD_MOTOR_STOP;
    update();
}

void EscDriver::update()
{
    esc->sendThrottle(throttleValue);
}