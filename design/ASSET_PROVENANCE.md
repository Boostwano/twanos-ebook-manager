# Artwork Provenance

The eight images under `design/banner-sources/` were created specifically for
Twano's eBook Manager through user-directed generative-image work during
development. They were not intentionally copied from a third-party image
library or another application.

The approved Twano splash and open leather-book logo under
`design/branding/` were created specifically for Twano through user-directed
generative-image work and selected by the project owner. Navigation symbols
remain application-specific drawn assets implemented for this project.
`twano-book-logo.ico` is a Windows icon-format derivative of the approved
open leather-book logo and is used by the application and installer.
`twano-splash-panel-rc1.png` is the project owner's approved tightly framed
crop of the same splash artwork. Its version line was removed, its four-pixel
rounded frame matches the cyan tagline, and pixels outside that frame are
transparent. At runtime Twano replaces only those authored corner areas with
an opaque dark fill and a crisp four-pixel square cyan frame, avoiding
pixelated rounded window edges while preserving the approved interior art.
The eight title-free backgrounds under `design/banner-backgrounds/` preserve
the selected banners' continuous left-to-right fades. The eight title PNGs
under `design/banner-title-overlays/` were created on 31 July 2026 and
converted from flat chroma-key backgrounds to alpha transparency. These
paired assets are used only for the responsive Twano banner compositor.

Before a public commercial release:

- retain the original generation records when available;
- perform a final visual similarity and trademark review;
- confirm that no later replacement asset came from an unlicensed source;
- record the final approved asset hashes with the release.

Downloaded book covers, provider logos, metadata images, Calibre plugin
archives, test ebooks, screenshots containing third-party content, and user
library files are not project artwork and must not be committed or bundled
unless their licence explicitly permits it.
