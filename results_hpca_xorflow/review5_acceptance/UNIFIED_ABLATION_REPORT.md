# Unified ablation

All requested variants use the frozen serializer/physical accounting. BEICSR_OPT and COMPLETE_XORFLOW are exact final schedules; COMPLETE_XORFLOW matches the primary byte/cycle row exactly for every checkpoint. Other variant cycle rows reuse frozen variant ratios plus the newly charged consumer delta and are labeled accordingly rather than misrepresented as fresh event traces.
