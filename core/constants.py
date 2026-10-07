"""
Shared Constants and Installer Templates for PureGoogleGappsBuilder
Compatible with Android 9.0.0 to 15.0.0 (Pie to VanillaIceCream)
"""

BRANCH_MAP = {
    "9.0.0": "pi",
    "10.0.0": "qoppa",
    "11.0.0": "rho",
    "12.0.0": "sigma",
    "12.1.0": "sigma",
    "13.0.0": "tau",
    "14.0.0": "upsilon",
    "15.0.0": "vic",
    "16.0.0": "baklava",
}

SDK_MAP = {
    "9.0.0": 28,
    "10.0.0": 29,
    "11.0.0": 30,
    "12.0.0": 31,
    "12.1.0": 32,
    "13.0.0": 33,
    "14.0.0": 34,
    "15.0.0": 35,
    "16.0.0": 36,
}

ARCH_TO_TOYBOX = {
    "x86_64": "toybox-x86_64",
    "x86": "toybox-x86",
    "arm64": "toybox-arm64",
    "arm64-v8a": "toybox-arm64",
    "arm": "toybox-arm",
    "armeabi-v7a": "toybox-arm"
}

ABI_TO_LIB_DIR = {
    "arm64-v8a": "arm64",
    "arm64": "arm64",
    "armeabi-v7a": "arm",
    "armeabi": "arm",
    "arm": "arm",
    "x86_64": "x86_64",
    "x86": "x86"
}

TARGET_APP_PATTERNS = [
    "*PrebuiltGmsCore*",
    "*GmsCore*",
    "*Phonesky*",
    "*GoogleServicesFramework*",
    "*GooglePartnerSetup*",
    "*PartnerSetupPrebuilt*",
    "*GoogleFeedback*",
    "*GoogleBackupTransport*",
    "*GoogleRestore*",
    "*GoogleRestorePrebuilt*",
    "*AndroidMigrate*",
    "*AndroidMigratePrebuilt*",
    "*GoogleOneTimeInitializer*",
    "*GoogleContactsSyncAdapter*",
    "*GoogleCalendarSyncAdapter*",
    "*PrebuiltExchange3Google*",
    "*Exchange3Google*",
    "*SpeechServicesByGoogle*",
    "*GoogleTTS*",
    "*talkback*",
    "*WellbeingPrebuilt*",
    "*Wellbeing*",
    "*AndroidAutoStub*",
    "*AndroidAutoStubPrebuilt*",
    "*SetupWizard*",
    "*SetupWizardPrebuilt*",
    "*Velvet*",
    "*GoogleExtShared*",
    "*GooglePackageInstaller*",
    "*MarkupGoogle*",
    "*SoundPickerPrebuilt*",
    "*libjni_latinimegoogle*",
    "*privapp-permissions-google*",
    "*permissions*google*",
    "*permissions*gms*",
    "*permissions*maps*",
    "*permissions*widevine*",
    "*sysconfig*google*",
    "*sysconfig*gms*",
    "*framework*google*",
    "*framework*maps*",
    "*dialer*"
]

PRIV_APPS_LIST = [
    "PrebuiltGmsCore",
    "GmsCore",
    "Phonesky",
    "GoogleServicesFramework",
    "GooglePartnerSetup",
    "PartnerSetupPrebuilt",
    "GoogleFeedback",
    "GoogleBackupTransport",
    "GoogleRestore",
    "GoogleRestorePrebuilt",
    "AndroidMigrate",
    "AndroidMigratePrebuilt",
    "GoogleOneTimeInitializer",
    "GoogleExtShared",
    "GooglePackageInstaller",
    "SetupWizard",
    "SetupWizardPrebuilt",
    "Velvet",
    "AndroidAutoStub",
    "AndroidAutoStubPrebuilt",
    "Wellbeing",
    "WellbeingPrebuilt"
]

EXCLUDED_AOSP_APPS = {
    "framework-res.apk", "settings.apk", "settingsgoogle.apk", "settingsprovider.apk", "systemui.apk",
    "systemuigoogle.apk", "telephonyprovider.apk", "telecom.apk", "teleservice.apk", "shell.apk",
    "certinstaller.apk", "keychain.apk", "camera2.apk", "gallery2.apk", "music.apk", "musicfx.apk",
    "stk.apk", "pacprocessor.apk", "htmlviewer.apk", "easteregg.apk", "downloadprovider.apk",
    "downloadproviderui.apk", "contactsprovider.apk", "calendarprovider.apk", "userdictionaryprovider.apk",
    "sharedstoragebackup.apk", "calllogbackup.apk", "managedprovisioning.apk", "externalstorageprovider.apk",
    "printspooler.apk", "carrierdefaultapp.apk", "traceur.apk", "companiondevicemanager.apk", "basicdreams.apk",
    "cameraextensionsproxy.apk", "simappdialog.apk", "vpnprocess.apk", "vpndialogs.apk", "localtransport.apk",
    "soundpicker.apk", "ons.apk", "mmsservice.apk", "credentialmanager.apk", "dynamicsysteminstallationservice.apk",
    "intentresolver.apk", "mtpservice.apk", "inputdevices.apk", "deviceaswebcam.apk", "phototable.apk",
    "blockednumberprovider.apk", "builtinprintservice.apk", "backuprestoreconfirmation.apk", "livewallpaperspicker.apk",
    "mediaproviderlegacy.apk", "fusedlocation.apk", "e2eecontactkeysprovider.apk", "devicediagnostics.apk",
    "cellbroadcastlegacyapp.apk", "proxyhandler.apk", "secureelement.apk", "carrierconfig.apk", "themepicker.apk",
    "cfsatelliteservice.apk", "multidisplayprovider.apk", "storagemanager.apk", "wallpapercropper.apk",
    "googlesdksetup.apk", "emulationradioconfig.apk", "taggoogle.apk"
}

ADDOND_HEAD = """#!/sbin/sh
#
# ADDOND_VERSION=3
#
# /system/addon.d/30-gapps.sh
#
. /tmp/backuptool.functions

list_files() {
cat <<EOF
"""

ADDOND_TAIL = """EOF
}

case "$1" in
  backup)
    list_files | while read FILE DUMMY; do
      backup_file "$S/$FILE"
    done
  ;;
  restore)
    list_files | while read FILE REPLACEMENT; do
      R=""
      [ -n "$REPLACEMENT" ] && R="$S/$REPLACEMENT"
      [ -f "$C/$S/$FILE" ] && restore_file "$S/$FILE" "$R"
    done
  ;;
  pre-backup)
    # Stub
  ;;
  post-backup)
    # Stub
  ;;
  pre-restore)
    # Stub
  ;;
  post-restore)
    for i in $(list_files); do
      f=$(get_output_path "$S/$i")
      chown root:root "$f" 2>/dev/null || true
      chmod 644 "$f" 2>/dev/null || true
      chmod 755 "$(dirname "$f")" 2>/dev/null || true
    done
    chmod 755 "$S/addon.d/30-gapps.sh" 2>/dev/null || true
  ;;
esac
"""
