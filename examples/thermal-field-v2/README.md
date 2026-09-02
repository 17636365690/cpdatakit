# Thermal-field v2 reference case

This small, format-neutral fixture is the planned N-dimensional reference for CPDataKit v0.6. It
contains a temperature field with dimensions `time=4`, `y=3`, and `x=4`, three unit-labelled
coordinates, and a string stage coordinate. Every value follows the recorded formula:

```text
273.15 + 10*time_index + 2*y_index + x_index
```

The JSON is a contract fixture, not an input accepted by the v0.5 tabular reader. The later v0.6
format adapters will write and read equivalent HDF5 2.0, NetCDF, and Zarr 3 artifacts. The existing
thermal-cycle table remains the lossless tabular conversion case. The malformed files document why
an ambiguous record axis or object-valued array must fail instead of being flattened.
