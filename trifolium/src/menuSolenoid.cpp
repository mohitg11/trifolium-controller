#include "menuCore.h"
#include "enumIds.h"

static NumericItem<uint16_t> solenoidExtendHighItem("Extend @ High V (ms)",
                                                    "device:solenoidExtendTimeHigh_ms",
                                                    &deviceSettings.solenoidExtendTimeHigh_ms, 0,
                                                    60, 1);
static NumericItem<uint16_t> solenoidExtendLowItem("Extend @ Low V (ms)",
                                                   "device:solenoidExtendTimeLow_ms",
                                                   &deviceSettings.solenoidExtendTimeLow_ms, 0, 60,
                                                   1);

class SolenoidThresholdItem : public MenuItem
{
  public:
    SolenoidThresholdItem(const char* label, const char* key, uint32_t* value, bool isHigh)
        : MenuItem(label, key), value_(value), isHigh_(isHigh)
    {
    }

    String valueText() const override { return String(*value_); }
    MenuActivation activate() override { return MenuActivation::EnterEdit; }
    void beginEdit() override { entryValue_ = *value_; }
    void adjust(int8_t direction, bool wrap) override
    {
        ItemBounds b;
        bounds(b);
        *value_ = (uint32_t)steppedToGrid(*value_, direction, b.step, b.lo, b.hi, wrap);
    }
    void cancelEdit() override { *value_ = entryValue_; }

    ItemKind kind() const override { return ItemKind::Int; }
    bool bounds(ItemBounds& out) const override
    {
        const int64_t cells = cellCount(deviceSettings.batteryType);
        const int64_t cutoff = (int64_t)deviceSettings.lowVoltageCutoffPerCell_mv;
        const int64_t packMax = batteryVoltageMax_mv[deviceSettings.batteryType];

        int64_t lo, hi;
        if (isHigh_)
        {
            lo = cells * cutoff;
            hi = packMax;
        }
        else
        {
            lo = cells * (cutoff - 1000);
            hi = (int64_t)deviceSettings.solenoidExtendTimeHighVoltage_mv - kStep;
        }
        if (hi < lo) // only reachable from an out-of-range High that hasn't been clamped yet
            hi = lo;
        out = {lo, hi, kStep, 0};
        return true;
    }
    void clampToBounds() override
    {
        ItemBounds b;
        bounds(b);
        clampInto(value_, b);
    }

  private:
    static const int64_t kStep = 10;
    uint32_t* value_;
    bool isHigh_;
    uint32_t entryValue_ = 0;
};

static SolenoidThresholdItem
    solenoidHighVoltageItem("High V Threshold (mV)", "device:solenoidExtendTimeHighVoltage_mv",
                            &deviceSettings.solenoidExtendTimeHighVoltage_mv, true);
static SolenoidThresholdItem
    solenoidLowVoltageItem("Low V Threshold (mV)", "device:solenoidExtendTimeLowVoltage_mv",
                           &deviceSettings.solenoidExtendTimeLowVoltage_mv, false);

static NumericItem<uint16_t> solenoidRetractItem("Retract Time (ms)",
                                                 "device:solenoidRetractTime_ms",
                                                 &deviceSettings.solenoidRetractTime_ms, 0, 100, 1);
static NumericItem<uint16_t> vibrationPulseItem("Vibration Pulse (ms)", "device:vibrationPulseMs",
                                                &deviceSettings.vibrationPulseMs, 0, 20, 1);

static NumericItem<uint16_t> motorVoltageItem("Motor Voltage (mV)", "device:pusherMotorVoltage_mv",
                                              &deviceSettings.pusherMotorVoltage_mv, 3000, 25200,
                                              100);
static NumericItem<uint16_t> turnTimeItem("Turn Time (ms)", "device:pusherTurnTime_ms",
                                          &deviceSettings.pusherTurnTime_ms, 20, 500, 5);
static NumericItem<uint16_t> stallTimeItem("Stall Time (ms)", "device:pusherStallTime_ms",
                                           &deviceSettings.pusherStallTime_ms, 100, 2000, 50);

static const char* const pusherTypeLabels[] = {"None", "Solenoid", "Brushed Motor"};
static_assert(sizeof(pusherTypeLabels) / sizeof(pusherTypeLabels[0]) == kPusherTypeIdCount, "pusherTypeLabels is out of step");
static EnumItem<pusherType_t> pusherTypeItem("Pusher Type", "device:pusherType",
                                             &deviceSettings.pusherType, pusherTypeLabels,
                                             kPusherTypeIds, kPusherTypeIdCount,
                                             true /* needsReboot */);
static ToggleItem pusherReverseItem("Reverse Direction", "device:pusherReverseDirection",
                                    &deviceSettings.pusherReverseDirection);
static NumericItem<uint16_t> pusherDebounceItem("Cycle Debounce (ms)", "device:pusherDebounceTime_ms",
                                                &deviceSettings.pusherDebounceTime_ms, 0, 200, 1);
static ToggleItem dartSensingItem("Dart Sensing", "device:dartSensing", &deviceSettings.dartSensing);
static NumericItem<uint16_t> dartDebounceItem("Dart Debounce (ms)", "device:dartSwitchDebounce_ms",
                                              &deviceSettings.dartSwitchDebounce_ms, 0, 50, 1);
static NumericItem<uint16_t> dartWaitItem("Dart Wait (ms)", "device:dartWaitTimeout_ms",
                                          &deviceSettings.dartWaitTimeout_ms, 200, 5000, 100);
static NumericItem<uint16_t> minPushItem("Min Push (ms)", "device:minPushTime_ms",
                                         &deviceSettings.minPushTime_ms, 0, 60, 1);
static ToggleItem revOnlyWithDartItem("Rev Only With Dart", "device:revOnlyWithDart",
                                      &deviceSettings.revOnlyWithDart);

// The stored pin, like ledIsWired() in menuDevice.cpp, so the rule beside it can say the same.
static bool dartSwitchIsWired()
{
    return deviceSettings.dartSwitchPin != PIN_NOT_USED;
}
static constexpr VisibilityTerm kDartSwitchWiredTerms[] = {{"device:dartSwitchPin", "255", true}};
static constexpr VisibilityCondition kDartSwitchWired = {kDartSwitchWiredTerms, 1};

static bool dartSensingIsOn()
{
    return deviceSettings.dartSwitchPin != PIN_NOT_USED && deviceSettings.dartSensing;
}
static constexpr VisibilityTerm kDartSensingOnTerms[] = {{"device:dartSwitchPin", "255", true},
                                                         {"device:dartSensing", "true", false}};
static constexpr VisibilityCondition kDartSensingOn = {kDartSensingOnTerms, 2};

// A crank turn cannot end early, so a brushed pusher has no Min Push.
static bool pushCanEndOnDart()
{
    return deviceSettings.dartSwitchPin != PIN_NOT_USED && deviceSettings.dartSensing &&
           deviceSettings.pusherType != PUSHER_BRUSHED_MOTOR;
}
static constexpr VisibilityTerm kPushCanEndOnDartTerms[] = {
    {"device:dartSwitchPin", "255", true},
    {"device:dartSensing", "true", false},
    {"device:pusherType", "brushed_motor", true}};
static constexpr VisibilityCondition kPushCanEndOnDart = {kPushCanEndOnDartTerms, 3};

static bool pusherIsSolenoid()
{
    return deviceSettings.pusherType == PUSHER_SOLENOID_OPENLOOP;
}
static constexpr VisibilityTerm kPusherIsSolenoidTerms[] = {
    {"device:pusherType", "solenoid_openloop", false}};
static constexpr VisibilityCondition kPusherIsSolenoid = {kPusherIsSolenoidTerms, 1};

static bool pusherIsBrushed()
{
    return deviceSettings.pusherType == PUSHER_BRUSHED_MOTOR;
}
static constexpr VisibilityTerm kPusherIsBrushedTerms[] = {
    {"device:pusherType", "brushed_motor", false}};
static constexpr VisibilityCondition kPusherIsBrushed = {kPusherIsBrushedTerms, 1};

// With 3D off the brushed motor only runs forward, and a vibration pulse would turn its crank.
static bool pusherIsNotBrushed()
{
    return deviceSettings.pusherType != PUSHER_BRUSHED_MOTOR;
}
static constexpr VisibilityTerm kPusherIsNotBrushedTerms[] = {
    {"device:pusherType", "brushed_motor", true}};
static constexpr VisibilityCondition kPusherIsNotBrushed = {kPusherIsNotBrushedTerms, 1};

struct SolenoidItemsInit
{
    SolenoidItemsInit()
    {
        solenoidExtendHighItem.setVisibleWhen(pusherIsSolenoid, &kPusherIsSolenoid);
        solenoidHighVoltageItem.setVisibleWhen(pusherIsSolenoid, &kPusherIsSolenoid);
        solenoidExtendLowItem.setVisibleWhen(pusherIsSolenoid, &kPusherIsSolenoid);
        solenoidLowVoltageItem.setVisibleWhen(pusherIsSolenoid, &kPusherIsSolenoid);
        pusherReverseItem.setVisibleWhen(pusherIsNotBrushed, &kPusherIsNotBrushed);
        solenoidRetractItem.setVisibleWhen(pusherIsNotBrushed, &kPusherIsNotBrushed);
        vibrationPulseItem.setVisibleWhen(pusherIsNotBrushed, &kPusherIsNotBrushed);
        motorVoltageItem.setVisibleWhen(pusherIsBrushed, &kPusherIsBrushed);
        turnTimeItem.setVisibleWhen(pusherIsBrushed, &kPusherIsBrushed);
        stallTimeItem.setVisibleWhen(pusherIsBrushed, &kPusherIsBrushed);
        pusherDebounceItem.setVisibleWhen(pusherIsBrushed, &kPusherIsBrushed);
    }
} solenoidItemsInit;

static MenuItem* solenoidItems[] = {
    &pusherTypeItem,         &pusherReverseItem,       &solenoidRetractItem,
    &solenoidExtendHighItem, &solenoidHighVoltageItem, &solenoidExtendLowItem,
    &solenoidLowVoltageItem, &vibrationPulseItem,      &motorVoltageItem,
    &turnTimeItem,           &stallTimeItem,           &pusherDebounceItem,
};
// Non-static: referenced by menu.cpp's Advanced submenu assembly.
SubmenuItem solenoidSubmenu("Solenoid / Pusher", solenoidItems,
                            sizeof(solenoidItems) / sizeof(solenoidItems[0]));


static MenuItem* dartItems[] = {
    &dartSensingItem, &revOnlyWithDartItem, &dartDebounceItem, &dartWaitItem, &minPushItem,
};
SubmenuItem dartSwitchSubmenu("Dart Switch", dartItems, sizeof(dartItems) / sizeof(dartItems[0]));
struct DartItemsInit
{
    DartItemsInit()
    {
        dartSwitchSubmenu.setVisibleWhen(dartSwitchIsWired, &kDartSwitchWired);
        dartSensingItem.setVisibleWhen(dartSwitchIsWired, &kDartSwitchWired);
        revOnlyWithDartItem.setVisibleWhen(dartSwitchIsWired, &kDartSwitchWired);
        dartDebounceItem.setVisibleWhen(dartSwitchIsWired, &kDartSwitchWired);
        dartWaitItem.setVisibleWhen(dartSensingIsOn, &kDartSensingOn);
        minPushItem.setVisibleWhen(pushCanEndOnDart, &kPushCanEndOnDart);
    }
} dartItemsInit;
