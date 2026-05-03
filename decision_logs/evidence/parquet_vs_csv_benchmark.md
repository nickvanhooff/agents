# Benchmark: CSV vs Parquet — groepsgenoot meting

Gemeten door groepsgenoot op zijn embedding pipeline (kleinere dataset, 999 items).

```
Metric                              CSV        Parquet     Winner
--------------------------------------------------------------------
File size (KB)                    181.0        111.4       parquet
Avg pipeline time (ms)          39294.6      36850.7      parquet
Peak memory (KB)                 6560.5       6426.1      parquet
Items in DB                         999          999
--------------------------------------------------------------------
```

**Conclusie:** Parquet is op alle drie de dimensies beter — 38% kleiner bestand, ~6% snellere gemiddelde pipelinetijd, ~2% minder geheugen. Gemeten op een kleinere dataset; verwacht effect neemt toe bij 15.000 rijen.
