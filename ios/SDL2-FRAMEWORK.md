# iOS SDL2 framework

Saturn vendors the upstream SDL2 source as a pinned Git submodule at `external/SDL2`.
The upstream project includes the official iOS framework project:

`external/SDL2/Xcode/SDL/SDL.xcodeproj`

and the shared schemes `Framework-iOS` and `xcFramework-iOS`.

## Checkout

Always initialize submodules when cloning:

```sh
git clone --recurse-submodules https://github.com/zeyadb-maker/Saturn.git
# or, inside an existing checkout:
git submodule update --init --recursive
```

The submodule is pinned to SDL release 2.30.11 (commit
`fa24d868ac2f8fd558e4e914c9863411245db8fd`).

## Build the iOS SDL framework

On a Mac with Xcode installed:

```sh
xcodebuild -project external/SDL2/Xcode/SDL/SDL.xcodeproj \
  -scheme Framework-iOS -sdk iphoneos \
  -configuration Release -destination 'generic/platform=iOS' build
```

For a simulator framework, use `-sdk iphonesimulator` and
`-destination 'generic/platform=iOS Simulator'`.

This supplies the SDL2 iOS framework project and source. It does **not** by itself
create the Saturn app target or an IPA; the app project must link the built SDL2
framework and compile Saturn's C/C++ sources with iOS-compatible settings.
