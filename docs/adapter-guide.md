# Adapter guide

An adapter translates one documented external representation into `Dataset`. Subclass
`cpdatakit.adapters.DatasetAdapter`, accept `pathlib.Path`, and return data plus explicit units and
conventions. Keep the integration in an optional package/extra; never add DAMASK, Abaqus, or a
commercial runtime to core dependencies.

## Acceptance checklist

An adapter proposal should satisfy every item before contribution:

- [ ] Official format evidence identifies the source specification, documentation, or reference
      implementation being supported.
- [ ] License and redistribution review confirms that the adapter and every fixture can be
      distributed under the project's terms.
- [ ] Upstream version coverage lists the tested source versions and documents unsupported ones.
- [ ] Synthetic or redistribution-approved fixtures cover the supported representation without
      requiring private or commercial data.
- [ ] Units and scientific conventions are explicit, including identifiers, tensor component
      order, orientation representations, and stress/strain measures when relevant.
- [ ] Tests are deterministic and run offline without network access, solver runtimes, GPUs, or
      personal filesystem paths.
- [ ] Ambiguous or unsupported conventions fail clearly instead of being inferred silently.
- [ ] Solver runtimes and other format-specific heavy dependencies stay out of CPDataKit core
      dependencies by using an optional package or extra.

Do not label a generic HDF5 reader as a DADF5 reader and do not claim ODB support without a
legitimately testable Abaqus environment.

