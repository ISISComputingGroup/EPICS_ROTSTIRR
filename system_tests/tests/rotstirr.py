import os
import time
import unittest

from parameterized import parameterized
from utils.channel_access import ChannelAccess
from utils.ioc_launcher import get_default_ioc_dir
from utils.test_modes import TestModes
from utils.testing import get_running_lewis_and_ioc, skip_if_devsim

ROTSTIRR_PREFIX = "ROTSTIRR_01"
TTIPLP_PREFIX = "TTIPLP_01"

IOCS = [
    {
        "name": ROTSTIRR_PREFIX,
        "directory": get_default_ioc_dir("ROTSTIRR"),
        "macros": {
            "VOLTMAX": 15,
            "RPMMAX": 41
        },
        "emulator": "Rotstirr",
    },
    {
        "name": TTIPLP_PREFIX,
        "directory": get_default_ioc_dir("TTIPLP"),
        "macros": {},
        "emulator": "ttiplp",
    },
]

TEST_MODES = [TestModes.RECSIM, TestModes.DEVSIM]

SETTINGS_DIR = os.path.join("C:/", "Instrument", "Settings", "config", "common", "rotating_stirrer_rack")
SETTINGS_FILE = "Default.txt"
file_headers = ("Voltage", "RPM")
file_settings = [(0, 0), (0, 4.999)] + [(3 + i, 5 + 3 * i) for i in range(13)]


class RotstirrTests(unittest.TestCase):
    """
    Tests for the Rotstirr IOC.
    """

    def setUp(self):
        self._lewis, self._ioc = get_running_lewis_and_ioc("Rotstirr", ROTSTIRR_PREFIX)
        self.ca_rotstirr = ChannelAccess(device_prefix=ROTSTIRR_PREFIX)
        self.ca_ttiplp = ChannelAccess(device_prefix=TTIPLP_PREFIX)

    def write_test_settings_file(self):
        if not os.path.exists(SETTINGS_DIR):
            os.mkdir(SETTINGS_DIR)
        with open(os.path.join(SETTINGS_DIR, SETTINGS_FILE), "w") as f:
            f.write("{}\n".format(" ".join(str(header) for header in file_headers)))
            for row in file_settings:
                f.write("{}\n".format(" ".join(str(setpoint) for setpoint in row)))
        time.sleep(5)

    def set_example_rpm_setting(self):
        self.write_test_settings_file()
        self.ca_rotstirr.assert_setting_setpoint_sets_readback(file_settings[4][1], "RPM:SP", "RPM:SP")

    def test_WHEN_rpm_first_set_THEN_overcurr_and_overvolt_set(self):
        self.set_example_rpm_setting()
        overvolt_expected = IOCS[0]["macros"]["VOLTMAX"]
        overcurr_expected = 1.1
        self.ca_ttiplp.assert_that_pv_is("OVERVOLT:SP", overvolt_expected)
        self.ca_ttiplp.assert_that_pv_is("OVERCURR:SP", overcurr_expected)

    def test_WHEN_stop_rotation_button_pressed_THEN_voltage_and_rotations_are_zero(self):
        self.set_example_rpm_setting()
        self.ca_rotstirr.set_pv_value("ROTSTOP.PROC", 1)
        self.ca_ttiplp.assert_that_pv_is("VOLTAGE:SP", 0)
        self.ca_rotstirr.assert_that_pv_is("CALC:RPM", 0)

    @parameterized.expand(file_settings)
    def test_WHEN_config_file_read_THEN_convert_correctly(self, volt_setpoint, rpm_setpoint):
        self.write_test_settings_file()
        self.ca_rotstirr.assert_setting_setpoint_sets_readback(rpm_setpoint, "CONVT:VOLT", "RPM:SP", volt_setpoint)
        self.ca_ttiplp.assert_that_pv_is("VOLTAGE:SP", volt_setpoint)

    def test_WHEN_rotations_set_over_limit_THEN_maximum_rotation_set(self):
        self.write_test_settings_file()
        rpm_max = IOCS[0]["macros"]["RPMMAX"]
        self.ca_rotstirr.assert_setting_setpoint_sets_readback(rpm_max + 5, "RPM:SP", "RPM:SP", rpm_max)

    @parameterized.expand([(item[1],) for item in file_settings[2:]])
    @skip_if_devsim("Behaviour not modelled in devsim")
    def test_WHEN_rotation_set_THEN_correct_rotation_read_back(self, rpm_setpoint):
        self.write_test_settings_file()
        self.ca_rotstirr.assert_setting_setpoint_sets_readback(rpm_setpoint, "CALC:RPM", "RPM:SP", rpm_setpoint)

    @skip_if_devsim("Behaviour not modelled in devsim")
    def test_WHEN_rotation_set_THEN_rotations_total_correctly_calculated(self):
        self.write_test_settings_file()
        rpm_setpoint = file_settings[-1][1]
        time_waiting = 10
        rotations_expected = round(rpm_setpoint / 60 * time_waiting)
        rotations_received = 0
        self.ca_rotstirr.set_pv_value("ROTS:TOTAL:RBV", 0)
        self.ca_rotstirr.set_pv_value("RPM:SP", rpm_setpoint)
        rotation_found = False
        # Give it some leeway as SCAN is set to 1 second on this
        time.sleep(time_waiting - 2)
        for a in range(5):
            rotations_received = round(self.ca_rotstirr.get_pv_value("ROTS:TOTAL:RBV"))
            if rotations_expected == rotations_received:
                rotation_found = True
                break
            time.sleep(1)
        self.assertTrue(rotation_found, "Total rotations not achieved within permitted time (current: " +
                        str(rotations_received) + ", expected: " + str(rotations_expected))
