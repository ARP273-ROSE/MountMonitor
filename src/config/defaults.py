"""Default configuration values for MountMonitor."""

DEFAULTS = {
    # General
    "observatory_name": "My Observatory",
    "mount_name": "",
    "mount_protocol": "lx200",  # lx200, lx200_serial, ascom, simulation
    "mount_ip": "192.168.1.1",
    "mount_port": 3492,
    "serial_port": "",
    # 9600 bauds : la valeur de sortie d'usine des 10Micron. La monture
    # permet d'en changer dans son menu, et la liaison est alors muette
    # tant que les deux bouts ne sont pas d'accord.
    "serial_baudrate": 9600,
    "ascom_driver": "",
    "language": "auto",  # auto, fr, en

    # Processing
    "polling_frequency_hz": 2.0,
    "running_range_seconds": 60,  # 60, 120, 300, 900
    "correct_graphs_for_range": True,
    "reference_mode": "median",  # median, target
    "tolerance_ra_arcsec": 1.5,
    "tolerance_dec_arcsec": 1.5,
    "tolerance_as_ha_seconds": False,
    "tolerance_seismic_percent": 5.0,
    "axial_mode": "off",  # off, velocity, displacement
    "log_mode": "all",  # all, tracking_only
    "delay_after_slew_seconds": 0,
    "history_lines": 50,
    "reset_mode": "manual",  # manual, slewing
    # manual, slewing, parking, full
    # « full » reproduit le comportement du MountMonitor Java : une image
    # est enregistree chaque fois que la largeur du graphe s'est remplie
    # de donnees neuves, ce qui laisse un carnet photographique continu
    # de la nuit.
    "dump_mode": "manual",
    "close_files_mode": "manual",  # manual, slewing, parking

    # Auxiliary - NTP
    "ntp_enabled": False,
    "ntp_server": "time.nist.gov",
    "ntp_interval_seconds": 30,

    # Auxiliary - Seismometer
    "seismometer_enabled": False,
    "seismometer_port": "",
    "seismometer_frequency_hz": 20,
    "seismometer_offset": 300,
    "seismometer_range": 2000,

    # Mount checks
    "check_refraction_enabled": True,
    "check_refraction_value": "continuously_updating",
    "check_tracking_rate": True,
    "check_tracking_rate_value": "sidereal",
    "check_gps_sync": False,
    "check_gps_sync_value": "synchronising",
    "check_dual_tracking": False,
    "check_dual_tracking_value": "disabled",

    # Layout
    "graph_textbox_ratio": 4,
    "horizontal_zoom": 1,
    "vertical_zoom_mode": "data",  # data, tolerance, maximum, minmax
    "window_width": 1400,
    "window_height": 850,
    "window_x": 100,
    "window_y": 100,
    "fft_width": 930,
    "fft_height": 426,
    "fft_x": 100,
    "fft_y": 100,
}
