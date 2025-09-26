# Workaround for stupid upstream image

The official upstream image, `mcr.microsoft.com/playwright`, doesn't actually include playwright. I know, right? They want to run...

```sh
npx -y playwright@1.55.0 run-server --port 3000 --host 0.0.0.0
```

...which uses `npx` to download and run playwright. In an environment with read-only container filesystems, this doesn't fly. The `Containerfile` in this directory builds an image that actually includes `playwright` so that a writeable filesystem isn't necessary at runtime.
