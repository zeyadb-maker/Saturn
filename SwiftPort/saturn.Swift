import Foundation
import SDL

// MARK: - Global Variables & State

var marioExists: Bool = false

var cameraFrozen: Bool = true
var cameraSpeed: Float = 0.0f
var cameraFocus: Float = 1.0f
var cameraSavestateMult: Float = 1.0f
var cameraFovSmooth: Bool = false
var isCameraMoving: Bool = false

var cameraViewEnabled: Bool = false
var cameraViewMoving: Bool = false
var cameraViewZooming: Bool = false
var cameraViewRotating: Bool = false
var cameraViewMoveX: Int = 0
var cameraViewMoveY: Int = 0

var enableHeadRotations: Bool = false
var enableTorsoRotation: Bool = true
var runSpeed: Float = 127.0f
var canFallAsleep: Bool = false
var saturnModelState: Int = 0
var linkMarioScale: Bool = true
var isSpinning: Bool = false
var spinMult: Float = 1.0f

var usingChainer: Bool = false
var chainerIndex: Int = 0
var selectedAnimation: MarioAnimID = .breakdance
var currentAnimFrame: Int = 0
var currentAnimId: Int = 0
var currentAnimLength: Int = 0
var isAnimPlaying: Bool = false
var isAnimPaused: Bool = false
var pausedAnimFrame: Int = 0

var currentAnimation = AnimationState(
    custom: false,
    hang: false,
    loop: false,
    speed: 1,
    id: .running
)

var thisFaceAngle: Float = 0.0f
var limitFps: Bool = true

// Discord
var hasDiscordInit: Bool = false

// Private state
var isChromaKeying: Bool = false
var prevQuicks: [Bool] = [false, false, false]
var lastCourseNum: Int = -1
var saturnLaunchTimer: Int = 0

var activeKeyFloatValue: Float = cameraFov
var activeKeyBoolValue: UnsafeMutablePointer<Bool>? = nil

var activeDataType: Int32 = KEY_FLOAT
var keyframePlaying: Bool = false
var kPopoutOpen: Bool = false
var kPopoutFocused: Bool = false
var mcamTimer: Int = 0
var kCurrentFrame: Int = 0
var kPreviousFrame: Int = 0
var kCurrCurveType: Int = 0

var kCurrentAnim: Int = -1
var shouldUpdateCamFromKeyframes: Bool = false

// Dictionary mapping strings to a tuple of (KeyframeTimeline, [Keyframe])
var kFrameKeys: [String: (KeyframeTimeline, [Keyframe])] = [:]

var kLastPassedIndex: Int = 0
var kDistanceBetween: Int = 0
var kCurrentDistance: Int = 0
var kStaticIncreaseValue: Float = 0.0f
var kLastPlacedFrame: Int = 0
var kLoop: Bool = false
var kAnimatingCamera: Bool = false
var kCPos0Incr: Float = 0.0f
var kCPos1Incr: Float = 0.0f
var kCPos2Incr: Float = 0.0f
var kCFoc0Incr: Float = 0.0f
var kCFoc1Incr: Float = 0.0f
var kCFoc2Incr: Float = 0.0f
var kCRot0Incr: Float = 0.0f
var kCRot1Incr: Float = 0.0f
var kCRot2Incr: Float = 0.0f
var hasSetInitialKFrames: Bool = false

var isCcEditing: Bool = false

var autoChroma: Bool = false
var autoChromaLevel: Bool = false
var autoChromaObjects: Bool = false

var activatedToads: UInt8 = 0

var marioHeadrotYaw: Float = 0
var marioHeadrotPitch: Float = 0
var marioHeadrotSpeed: Float = 10.0f

let FREEZE_CAMERA: UInt32 = 0x0800
let CYCLE_EYE_STATE: UInt32 = 0x0100
let LOAD_ANIMATION: UInt32 = 0x0200
let TOGGLE_MENU: UInt32 = 0x0400

var chromaKeyColorR: UInt32 = 0
var chromaKeyColorG: UInt32 = 255
var chromaKeyColorB: UInt32 = 0

var autosaveDelay: Int = -1

var gChromaKeyColor: UInt16 = 0x07C1
var gChromaKeyBackground: UInt16 = 0

var keyResetter: Int = 0
var godmodeTempOff: Bool = false

var extractThreadBegan: Bool = false
var extractionFinished: Bool = false
var extractionProgress: Float = 1

// MARK: - Helper Functions

func keyIncreaseVal(vecfloat: [Float]) -> Float {
    let nextVal = vecfloat[kLastPassedIndex + 1]
    let thisVal = vecfloat[kLastPassedIndex]
    return (nextVal - thisVal) / Float(kDistanceBetween)
}

func timelineHasId(_ id: String) -> Bool {
    guard !kFrameKeys.isEmpty else { return false }
    for (_, entry) in kFrameKeys {
        for keyframe in entry.1 {
            if keyframe.timelineID == id {
                return true
            }
        }
    }
    return false
}

// MARK: - Saturn Machinima Functions

func saturnUpdate() {
    // Keybinds
    if marioExists {
        let keyboardState = SDL_GetKeyboardState(nil)
        
        if let controller = gPlayer1Controller, (controller.pointee.buttonPressed & UInt32(D_JPAD)) != 0 {
            showMenu = !showMenu
        }
        
        if keyResetter == 6 {
            if let keyboardState = keyboardState, keyboardState[Int(SDL_SCANCODE_F2.rawValue)] != 0 {
                if gMarioState.pointee.action == ACT_DEBUG_FREE_MOVE {
                    reset_camera(gCamera)
                    set_mario_action(gMarioState, ACT_IDLE, 0)
                } else {
                    set_mario_action(gMarioState, ACT_DEBUG_FREE_MOVE, 0)
                }
                keyResetter = 0
            }
        }
        
        if !saturn_disable_sm64_input() {
            if let controller = gPlayer1Controller {
                if (controller.pointee.buttonPressed & UInt32(U_JPAD)) != 0 { cameraFrozen.toggle() }
                if (controller.pointee.buttonPressed & UInt32(L_JPAD)) != 0 {
                    if !isAnimPlaying {
                        anim_play_button()
                    } else {
                        isAnimPaused.toggle()
                    }
                }
                if (controller.pointee.buttonPressed & UInt32(R_JPAD)) != 0 {
                    currentAnimation.loop.toggle()
                }
            }
        }
    }

    if keyResetter < 6 {
        keyResetter += 1
    }

    // Machinima
    machinimaMode = cameraFrozen ? 1 : 0
    machinimaKeyframing = (keyframePlaying && activeDataType == KEY_CAMERA)

    if cameraFrozen, !saturn_disable_sm64_input(), let keyboardState = SDL_GetKeyboardState(nil) {
        if configMCameraMode == 2 {
            cameraViewEnabled = keyboardState[Int(SDL_SCANCODE_LSHIFT.rawValue)] != 0
            var x: Int32 = 0, y: Int32 = 0
            let mouseState = SDL_GetMouseState(&x, &y)
            cameraViewMoving = (mouseState & UInt32(SDL_BUTTON(SDL_BUTTON_RIGHT))) != 0
            cameraViewZooming = (mouseState & UInt32(SDL_BUTTON(SDL_BUTTON_MIDDLE))) != 0
            cameraViewRotating = (mouseState & UInt32(SDL_BUTTON(SDL_BUTTON_LEFT))) != 0
        } else if configMCameraMode == 0 {
            let isRDown = keyboardState[Int(SDL_SCANCODE_R.rawValue)] != 0
            let disableInput = saturn_disable_sm64_input()
            
            let yKey = keyboardState[Int(SDL_SCANCODE_Y.rawValue)] != 0 && !disableInput
            let hKey = keyboardState[Int(SDL_SCANCODE_H.rawValue)] != 0 && !disableInput
            let gKey = keyboardState[Int(SDL_SCANCODE_G.rawValue)] != 0 && !disableInput
            let jKey = keyboardState[Int(SDL_SCANCODE_J.rawValue)] != 0 && !disableInput
            
            if isRDown {
                cameraRotateUp = yKey ? 1 : 0
                cameraRotateDown = hKey ? 1 : 0
                cameraRotateLeft = gKey ? 1 : 0
                cameraRotateRight = jKey ? 1 : 0
                
                cameraMoveForward = 0
                cameraMoveBackward = 0
                cameraMoveLeft = 0
                cameraMoveRight = 0
            } else {
                cameraMoveForward = yKey ? 1 : 0
                cameraMoveBackward = hKey ? 1 : 0
                cameraMoveLeft = gKey ? 1 : 0
                cameraMoveRight = jKey ? 1 : 0
                
                cameraRotateUp = 0
                cameraRotateDown = 0
                cameraRotateLeft = 0
                cameraRotateRight = 0
            }
            cameraMoveUp = keyboardState[Int(SDL_SCANCODE_T.rawValue)] != 0 && !disableInput
            cameraMoveDown = keyboardState[Int(SDL_SCANCODE_U.rawValue)] != 0 && !disableInput
        }
        cameraRollLeft = keyboardState[Int(SDL_SCANCODE_V.rawValue)] != 0 ? 1 : 0
        cameraRollRight = keyboardState[Int(SDL_SCANCODE_B.rawValue)] != 0 ? 1 : 0
    }

    if !keyframePlaying, !cameraFrozen {
        gLakituState.focHSpeed = cameraFocus * cameraSavestateMult * 0.8f
        gLakituState.focVSpeed = cameraFocus * cameraSavestateMult * 0.3f
        gLakituState.posHSpeed = cameraFocus * cameraSavestateMult * 0.3f
        gLakituState.posVSpeed = cameraFocus * cameraSavestateMult * 0.3f
    }

    camera_default_fov = camera_fov + 5.0f

    if gCurrLevelNum == LEVEL_SA || autoChroma {
        if !isChromaKeying { isChromaKeying = true }
    }
    if gCurrLevelNum != LEVEL_SA, !autoChroma {
        if !isChromaKeying { isChromaKeying = false }
    }

    if splash_finished { saturnLaunchTimer += 1 }
    
    if gCurrLevelNum == LEVEL_SA, saturnLaunchTimer <= 1, splash_finished {
        gMarioState.pointee.faceAngle.1 = 0
        if let camera = gCamera {
            var dist: Float = 0
            var yaw: Int16 = 0, pitch: Int16 = 0
            vec3f_set(camera.pointee.pos, 0.f, 192.f, 264.f)
            vec3f_set(camera.pointee.focus, 0.f, 181.f, 28.f)
            vec3f_copy(freezecamPos, camera.pointee.pos)
            vec3f_get_dist_and_angle(camera.pointee.pos, camera.pointee.focus, &dist, &pitch, &yaw)
            freezecamYaw = Float(yaw)
            freezecamPitch = Float(pitch)
            vec3f_copy(gLakituState.pos, camera.pointee.pos)
            vec3f_copy(gLakituState.focus, camera.pointee.focus)
            vec3f_copy(gLakituState.goalPos, camera.pointee.pos)
            vec3f_copy(gLakituState.goalFocus, camera.pointee.focus)
            camera.pointee.yaw = calculate_yaw(camera.pointee.focus, camera.pointee.pos)
            gLakituState.yaw = camera.pointee.yaw
        }
    }

    // Keyframes
    if !kPopoutOpen { kPopoutFocused = false }
    if keyframePlaying {
        if timelineHasId("k_c_camera_pos0") {
            gLakituState.focHSpeed = 15.f * cameraFocus * 0.8f
            gLakituState.focVSpeed = 15.f * cameraFocus * 0.3f
            gLakituState.posHSpeed = 15.f * cameraFocus * 0.3f
            gLakituState.posVSpeed = 15.f * cameraFocus * 0.3f
        }
        
        var end = true
        for (key, _) in kFrameKeys {
            if !saturn_keyframe_apply(key, mcamTimer) { end = false }
        }
        if end {
            if kLoop { mcamTimer = 0 }
            else { keyframePlaying = false }
        }

        if timelineHasId("k_angle") {
            gMarioState.pointee.faceAngle.1 = Int16(thisFaceAngle * 182.04f)
        }

        schroma_imgui_init()

        if !end {
            mcamTimer += 1
            kCurrentFrame = UInt32(mcamTimer)
        }
    }

    if cameraFrozen, keyframePlaying {
        shouldUpdateCamFromKeyframes = false
        if let camera = gCamera {
            vec3f_copy(camera.pointee.pos, freezecamPos)
            vec3f_set_dist_and_angle(camera.pointee.pos, camera.pointee.focus, 100, freezecamPitch, freezecamYaw)
            gLakituState.roll = freezecamRoll
            vec3f_copy(gLakituState.pos, camera.pointee.pos)
            vec3f_copy(gLakituState.focus, camera.pointee.focus)
            vec3f_copy(gLakituState.goalPos, camera.pointee.pos)
            vec3f_copy(gLakituState.goalFocus, camera.pointee.focus)
            camera.pointee.yaw = calculate_yaw(camera.pointee.focus, camera.pointee.pos)
            gLakituState.yaw = camera.pointee.yaw
        }
    }

    // Animations
    if marioExists {
        if isAnimPaused {
            gMarioState.pointee.marioObj.pointee.header.gfx.unk38.animFrame = Float(currentAnimFrame)
            gMarioState.pointee.marioObj.pointee.header.gfx.unk38.animFrameAccelAssist = Float(currentAnimFrame)
        } else if isAnimPlaying {
            if currentAnimation.hang {
                let unk08 = Int(gMarioState.pointee.marioObj.pointee.header.gfx.unk38.curAnim.pointee.unk08)
                if is_anim_past_frame(gMarioState, Int32(unk08 - 1)) {
                    isAnimPaused.toggle()
                }
            }

            let unk08 = Int(gMarioState.pointee.marioObj.pointee.header.gfx.unk38.curAnim.pointee.unk08)
            if is_anim_past_frame(gMarioState, Int32(unk08)) || is_anim_at_end(gMarioState) {
                if currentAnimation.loop, !usingChainer {
                    gMarioState.pointee.marioObj.pointee.header.gfx.unk38.animFrame = 0
                    gMarioState.pointee.marioObj.pointee.header.gfx.unk38.animFrameAccelAssist = 0
                } else {
                    if usingChainer {
                        chainerIndex += 1
                    } else {
                        if gMarioState.pointee.action == ACT_DEBUG_FREE_MOVE {
                            set_mario_animation(gMarioState, MARIO_ANIM_A_POSE)
                        }
                        isAnimPlaying = false
                        isAnimPaused = false
                    }
                }
            }

            currentAnimId = Int(gMarioState.pointee.marioObj.pointee.header.gfx.unk38.animID)
            if gMarioState.pointee.action == ACT_IDLE || gMarioState.pointee.action == ACT_FIRST_PERSON || gMarioState.pointee.action == ACT_DEBUG_FREE_MOVE {
                currentAnimFrame = Int(gMarioState.pointee.marioObj.pointee.header.gfx.unk38.animFrame)
                currentAnimLength = Int(gMarioState.pointee.marioObj.pointee.header.gfx.unk38.curAnim.pointee.unk08) - 1
            }

            if currentAnimation.speed != 1.0f {
                gMarioState.pointee.marioObj.pointee.header.gfx.unk38.animAccel = UInt16(currentAnimation.speed * 65535)
            }

            if usingChainer, isAnimPlaying {
                saturn_run_chainer()
            }
        }
    }

    // Misc
    marioExists = (gMarioState.pointee.action != ACT_UNINITIALIZED && sCurrPlayMode != 2 && mario_loaded)

    if !marioExists {
        isAnimPlaying = false
        isAnimPaused = false
    }

    switch saturnModelState {
    case 0: scrollModelState = 0
    case 1: scrollModelState = 0x200
    case 2: scrollModelState = 0x180
    case 3: scrollModelState = 0x380
    default: scrollModelState = 0
    }

    if linkMarioScale {
        marioScaleSizeY = marioScaleSizeX
        marioScaleSizeZ = marioScaleSizeX
    }

    if isSpinning, marioExists {
        gMarioState.pointee.faceAngle.1 += Int16(spinMult * 15 * 182.04f)
    }

    saturn_cmd_resume()

    // Autosave
    if gCurrLevelNum != LEVEL_SA || gCurrAreaIndex != 3 {
        if autosaveDelay <= 0 { autosaveDelay = 30 * configAutosaveDelay }
        autosaveDelay -= 1
        if autosaveDelay == 0 { saturn_save_project("autosave.spj") }
    }
}

func saturnKeyframeSetupInterpolation(id: String, frame: Int, keyframe: inout Int, last: inout Bool) -> Float {
    guard let pair = kFrameKeys[id] else { return 0.0 }
    let keyframes = pair.1

    for i in 0..<keyframes.count {
        if frame < keyframes[i].position { break }
        keyframe = i
    }

    last = (keyframe + 1 == keyframes.count)
    if last { keyframe -= 1 }

    var x = Float(frame - keyframes[keyframe].position) / Float(keyframes[keyframe + 1].position - keyframes[keyframe].position)
    if last {
        x = 1
    } else if keyframes[keyframe].curve == .SLOW {
        x = x * x
    } else if keyframes[keyframe].curve == .FAST {
        x = 1 - (1 - x) * (1 - x)
    } else if keyframes[keyframe].curve == .SMOOTH {
        x = x < 0.5 ? 2 * x * x : 1 - powf(-2 * x + 2, 2) / 2
    } else if keyframes[keyframe].curve == .WAIT {
        x = floorf(x)
    }

    return x
}

func saturn_keyframe_apply(_ id: String, _ frame: Int) -> Bool {
    guard let pair = kFrameKeys[id] else { return true }
    let timeline = pair.0
    let keyframes = pair.1

    if timeline.behavior == KFBEH_EVENT {
        if !keyframePlaying { return true }
        var idx = -1
        for i in 0..<keyframes.count {
            if keyframes[i].position == frame {
                idx = i
                break
            }
        }
        if idx == -1 { return keyframes.isEmpty }
        
        if timeline.type == KFTYPE_ANIM {
            if let dest = timeline.dest?.assumingMemoryBound(to: AnimationState.self) {
                dest.pointee.custom = keyframes[idx].value[0] >= 1
                dest.pointee.loop = keyframes[idx].value[1] >= 1
                dest.pointee.hang = keyframes[idx].value[2] >= 1
                dest.pointee.speed = keyframes[idx].value[3]
                dest.pointee.id = MarioAnimID(rawValue: Int(keyframes[idx].value[4])) ?? .running
                isAnimPlaying = false
                isAnimPaused = false
                usingChainer = false
                chainerIndex = 0
                anim_play_button()
            }
        }
        if timeline.type == KFTYPE_EXPRESSION {
            // Model expression mapping logic
        }
        return idx + 1 == keyframes.count
    }

    var values: [Float] = []
    var last = true
    if keyframes.count == 1 {
        values = keyframes[0].value
    } else {
        var keyframe = 0
        last = false
        let x = saturnKeyframeSetupInterpolation(id: id, frame: frame, keyframe: &keyframe, last: &last)
        for i in 0..<keyframes[keyframe].value.count {
            values.append((keyframes[keyframe + 1].value[i] - keyframes[keyframe].value[i]) * x + keyframes[keyframe].value[i])
        }
    }
    
    if timeline.type == KFTYPE_BOOL {
        if let dest = timeline.dest?.assumingMemoryBound(to: Bool.self) {
            dest.pointee = values[0] >= 1
        }
    }
    if timeline.type == KFTYPE_FLOAT {
        if let dest = timeline.dest?.assumingMemoryBound(to: Float.self) {
            dest.pointee = values[0]
        }
    }
    if timeline.type == KFTYPE_COLOR {
        if let dest = timeline.dest?.assumingMemoryBound(to: Float.self) {
            dest[0] = values[0]
            dest[1] = values[1]
            dest[2] = values[2]
        }
    }

    return last
}

func saturn_play_animation(_ anim: MarioAnimID) {
    force_set_mario_animation(gMarioState, anim)
    isAnimPlaying = true
}

func saturn_play_keyframe() {
    guard !kFrameKeys.isEmpty else { return }

    if !keyframePlaying {
        kLastPassedIndex = 0
        kDistanceBetween = 0
        kCurrentFrame = 0
        mcamTimer = 0
        keyframePlaying = true
    } else {
        if kCurrentFrame > 0 {
            keyframePlaying = false
        }
    }
}

// MARK: - Copy / Paste

var storedMarioPos = (Float(0), Float(0), Float(0))
var storedMarioAngle = (Int16(0), Int16(0), Int16(0))

func saturn_copy_mario() {
    vec3f_copy(&storedMarioPos, &gMarioState.pointee.pos)
    vec3s_copy(&storedMarioAngle, &gMarioState.pointee.faceAngle)
    vec3f_copy(&stored_camera_pos, &gCamera.pointee.pos)
    vec3f_copy(&stored_camera_focus, &gCamera.pointee.focus)
}

func saturn_paste_mario() {
    if machinimaCopying == 0 {
        vec3f_copy(&gMarioState.pointee.pos, &storedMarioPos)
        vec3f_copy(&gMarioState.pointee.marioObj.pointee.header.gfx.pos, &storedMarioPos)
        vec3s_copy(&gMarioState.pointee.faceAngle, &storedMarioAngle)
        vec3s_set(&gMarioState.pointee.marioObj.pointee.header.gfx.angle, 0, storedMarioAngle.1, 0)
    }
    machinimaCopying = 1
}

var posRelative = (Float(0), Float(0), Float(0))
var focRelative = (Int16(0), Int16(0), Int16(0))
var wasRelative: Bool = false

func saturn_copy_camera(_ relative: Bool) {
    if relative, let camera = gCamera {
        posRelative.0 = floorf(camera.pointee.pos.0 - gMarioState.pointee.pos.0)
        posRelative.1 = floorf(camera.pointee.pos.1 - gMarioState.pointee.pos.1)
        posRelative.2 = floorf(camera.pointee.pos.2 - gMarioState.pointee.pos.2)

        focRelative.0 = Int16(floorf(camera.pointee.focus.0 - gMarioState.pointee.pos.0))
        focRelative.1 = Int16(floorf(camera.pointee.focus.1 - gMarioState.pointee.pos.1))
        focRelative.2 = Int16(floorf(camera.pointee.focus.2 - gMarioState.pointee.pos.2))
    } else if let camera = gCamera {
        vec3f_copy(&stored_camera_pos, &camera.pointee.pos)
        vec3f_copy(&stored_camera_focus, &camera.pointee.focus)
    }
    wasRelative = relative
}

func saturn_paste_camera() {
    if wasRelative {
        stored_camera_pos.0 = floorf(gMarioState.pointee.pos.0 + posRelative.0)
        stored_camera_pos.1 = floorf(gMarioState.pointee.pos.1 + posRelative.1)
        stored_camera_pos.2 = floorf(gMarioState.pointee.pos.2 + posRelative.2)
        stored_camera_focus.0 = floorf(gMarioState.pointee.pos.0 + Float(focRelative.0))
        stored_camera_focus.1 = floorf(gMarioState.pointee.pos.1 + Float(focRelative.1))
        stored_camera_focus.2 = floorf(gMarioState.pointee.pos.2 + Float(focRelative.2))
    }
    machinimaCopying = 1
}

// MARK: - Debug & Utilities

func saturn_print(_ text: String) {
    if let keyboardState = SDL_GetKeyboardState(nil), keyboardState[Int(SDL_SCANCODE_RSHIFT.rawValue)] != 0 {
        print(text, terminator: "")
    }
}

func saturn_get_stage_name(_ courseNum: Int32) -> String {
    switch courseNum {
    case LEVEL_SA: return "Chroma Key Stage"
    case LEVEL_CASTLE: return "Peach's Castle"
    case LEVEL_CASTLE_GROUNDS: return "Castle Grounds"
    case LEVEL_CASTLE_COURTYARD: return "Castle Courtyard"
    case LEVEL_BOB: return "Bob-omb Battlefield"
    case LEVEL_CCM: return "Cool, Cool Mountain"
    case LEVEL_WF: return "Whomp's Fortress"
    case LEVEL_JRB: return "Jolly Roger Bay"
    case LEVEL_PSS: return "Princess's Secret Slide"
    case LEVEL_TOTWC: return "Tower of the Wing Cap"
    case LEVEL_BITDW: return "Bowser in the Dark World"
    case LEVEL_BBH: return "Big Boo's Haunt"
    case LEVEL_HMC: return "Hazy Maze Cave"
    case LEVEL_COTMC: return "Cavern of the Metal Cap"
    case LEVEL_LLL: return "Lethal Lava Land"
    case LEVEL_SSL: return "Shifting Sand Land"
    case LEVEL_VCUTM: return "Vanish Cap Under the Moat"
    case LEVEL_DDD: return "Dire, Dire Docks"
    case LEVEL_BITFS: return "Bowser in the Fire Sea"
    case LEVEL_SL: return "Snowman's Land"
    case LEVEL_WDW: return "Wet-Dry World"
    case LEVEL_TTM: return "Tall, Tall Mountain"
    case LEVEL_THI: return "Tiny, Huge Island"
    case LEVEL_TTC: return "Tick Tock Clock"
    case LEVEL_WMOTR: return "Wing Mario Over the Rainbow"
    case LEVEL_RR: return "Rainbow Ride"
    case LEVEL_BITS: return "Bowser in the Sky"
    default: return "Unknown"
    }
}

func saturnBeginExtractRomThread() -> Int32 {
    if extractThreadBegan { return extractionFinished ? 1 : 0 }
    extractThreadBegan = true
    extractionFinished = false
    
    DispatchQueue.global().async {
        saturn_extract_rom(EXTRACT_TYPE_ALL)
        extractionFinished = true
    }
    return 0
}

func saturn_do_load() {
    if (save_file_get_flags() & SAVE_FLAG_TALKED_TO_ALL_TOADS) == 0 {
        DynOS_Gfx_GetPacks().Clear()
    }
    DynOS_Opt_Init()
    saturn_imgui_init()
    saturn_load_locations()
    saturnLaunchTimer = 0
    saturn_cmd_registers_load()
    saturn_load_favorite_anims()
    saturn_fill_data_table()
}

func saturn_on_splash_finish() {
    splash_finished = true
}

func saturn_should_show_splash() -> Int32 {
    return configSaturnSplash ? 1 : 0
}

func saturnTimelineExists(_ name: String) -> Bool {
    return kFrameKeys[name] != nil
}
