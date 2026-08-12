# Adapter guide

An adapter translates one documented external representation into `Dataset`. Subclass
`cpdatakit.adapters.DatasetAdapter`, accept `pathlib.Path`, and return data plus explicit units and
conventions. Keep the integration in an optional package/extra; never add DAMASK, Abaqus, or a
commercial runtime to core dependencies.

Before contributing an adapter, verify source-format documentation and code/data licenses. Add
fixtures that are synthetic or redistribution-approved, record which upstream versions were
tested, fail on ambiguous scientific conventions, and test without network, solver, GPU, or
personal paths. Do not label a generic HDF5 reader as a DADF5 reader and do not claim ODB support
without a legitimately testable Abaqus environment.

