## 2024-05-18 - Batching numpy operations
**Learning:** Calling `np.percentile` 5 separate times inside a simulation loop is significantly slower than batching them into a single `np.percentile` call passing a list of percentiles (e.g. `[5, 25, 50, 75, 95]`). This gave a ~30% performance boost to the simulation engine.
**Action:** Always batch numpy operations whenever possible to minimize Python/C transition overhead.
