# Deprecated entry points

`pureref_gen.py` and `pureref_gen_script.py` are the original scripts this
project started as. They still work — they now call the `pureref` package — and
they are kept here so nothing that linked to them breaks:

```sh
python legacy/pureref_gen_script.py Artists Purs
```

The maintained equivalents are `pureref new` and `pureref batch`, which handle
2.x as well. The `purformat` package stays at the top level instead, because
old code imports it by name.
