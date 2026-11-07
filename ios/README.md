# Saturn iOS app target

This XcodeGen specification creates a native iOS application target named `Saturn`.
It compiles Saturn's C/C++ engine, PC SDL2 platform layer, editor sources, actors,
levels, data and the small libultra C compatibility set. It links and embeds the
official SDL2 iOS framework built from the pinned `external/SDL2` submodule.

## Generate and build (macOS + Xcode)

From the repository root:

```sh
brew install xcodegen
xcodebuild -project external/SDL2/Xcode/SDL/SDL.xcodeproj \
  -scheme Framework-iOS -sdk iphoneos -configuration Release \
  -destination 'generic/platform=iOS' \
  -derivedDataPath build/SDL2DerivedData CODE_SIGNING_ALLOWED=NO build
xcodegen generate --spec ios/project.yml --project ios/SaturnIOS.xcodeproj
xcodebuild -project ios/SaturnIOS.xcodeproj -scheme Saturn \
  -sdk iphoneos -configuration Release \
  -destination 'generic/platform=iOS' \
  -derivedDataPath build/SaturnDerivedData CODE_SIGNING_ALLOWED=NO build
```

The current repository does not contain an extracted SM64 asset set or a ROM.
The engine's existing startup checks for the user's own, legally obtained US ROM;
this target does not bundle copyrighted game data. The app target and SDL2 linkage
therefore still need a device/simulator build and startup validation, and the
iOS ROM-import flow remains a separate required integration.
