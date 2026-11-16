# Hardware-in-the-loop (manual, marker `hil`)

No test in this folder runs in CI: Station's automated suite uses only the mocks in
`hibiscus_station/mock/`. The hardware checklist lives in the user guide so lab users can fill it in:

* English: [`docs/user-guide/en/station-hardware-uat.md`](../../docs/user-guide/en/station-hardware-uat.md)
* Tiếng Việt: [`docs/user-guide/vi/station-hardware-uat.md`](../../docs/user-guide/vi/station-hardware-uat.md)

Items that confirm assumptions the code cannot check without a real SO-101 (spec §9.4, §11.1):

1. Units of `Present_Current` (6.5 mA per step) and the `Status` bit layout, both from Feetech's STS
   memory table and isolated in `hibiscus_station/hw/feetech.py`.
2. Measured sync-read latency per register (the scheduler assumes 1-3 ms for 6 motors; mocks use 1.5 ms).
3. Temperature ±2 °C against a thermometer, voltage ±0.2 V against a multimeter.
4. Overload status bit by stalling the gripper.
5. 10-minute teleop at 30 Hz with telemetry: overruns under 1 %.
6. Thermal stop by lowering `temp_critical_c` to the current temperature + 1.
7. E-stop latency under 100 ms (high-speed phone video).
8. Camera unplug during recording.
9. Calibration interop with `lerobot-teleoperate --robot.id=...` and LeLab, both ways.
10. Leader voltage warnings on a 5 V leader (`Min_Voltage_Limit` + 0.5 V rule).
