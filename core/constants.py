"""
Shared Constants and Installer Templates for PureGoogleGappsBuilder
"""

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
    "17.0.0": 37,
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
    "*privapp-permissions-google*",
    "*permissions*google*",
    "*permissions*gms*",
    "*permissions*maps*",
    "*permissions*widevine*",
    "*sysconfig*google*",
    "*sysconfig*gms*",
    "*framework*google*",
    "*framework*maps*"
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
    "googlesdksetup.apk", "emulationradioconfig.apk", "taggoogle.apk", "velvettitan.apk"
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

UPDATE_BINARY_SCRIPT = r"""#!/sbin/sh
# Universal GApps Recovery Installer for Android 9 - 15
# Compatible with Dynamic Partitions, SAR, and Legacy devices in TWRP / OrangeFox / Lineage / AOSP Recovery

OUTFD="/proc/self/fd/$2"
ZIP="$3"

set_con() {
  chcon -h u:object_r:"$1":s0 "$2" 2>/dev/null || true
  chcon u:object_r:"$1":s0 "$2" 2>/dev/null || true
}

set_perm() {
  chmod "$1" "$2" 2>/dev/null || true
}

set_owner() {
  chown "$1:$2" "$3" 2>/dev/null || true
}

ui_print() {
  echo "ui_print $1" > "$OUTFD"
  echo "ui_print" > "$OUTFD"
}

getprop2() {
  grep -m 1 "^$2=" "$1" 2>/dev/null | cut -d= -f2
}

ui_print "*****************************************"
ui_print "       Pure Google GApps Installer       "
ui_print "       100% Genuine Google Binaries      "
ui_print "*****************************************"

ui_print "[*] Extracting package payload..."
TMP=/tmp/gapps_installer
rm -rf "$TMP"
mkdir -p "$TMP"
cd "$TMP"
unzip -o "$ZIP" >/dev/null 2>&1

GAPPS_ARCH=$(getprop2 "$TMP/build.prop" arch)
CPU_ARCH=$(getprop ro.bionic.arch)
if [ -n "$GAPPS_ARCH" ] && [ -n "$CPU_ARCH" ] && [ "$GAPPS_ARCH" != "$CPU_ARCH" ]; then
  ui_print "[!] Warning: Package arch ($GAPPS_ARCH) differs from ro.bionic.arch ($CPU_ARCH)"
fi

ui_print "[*] Detecting and mounting system partitions..."
umount /system 2>/dev/null || true
umount /mnt/system 2>/dev/null || true
umount /product 2>/dev/null || true
umount /system_ext 2>/dev/null || true

DYNAMIC_PARTITIONS=$(getprop ro.boot.dynamic_partitions)
if [ "$DYNAMIC_PARTITIONS" = "true" ]; then
  BLK_PATH="/dev/block/mapper"
else
  BLK_PATH="/dev/block/bootdevice/by-name"
fi

CURRENTSLOT=$(getprop ro.boot.slot_suffix)
SLOT_SUFFIX=""
if [ -n "$CURRENTSLOT" ]; then
  SLOT_SUFFIX="$CURRENTSLOT"
fi

find_block() {
  name="$1"
  for dev in "${BLK_PATH}/${name}${SLOT_SUFFIX}" "${BLK_PATH}/${name}" "/dev/block/by-name/${name}${SLOT_SUFFIX}" "/dev/block/by-name/${name}"; do
    if [ -b "$dev" ]; then
      echo "$dev"
      return 0
    fi
  done
}

SYSTEM_BLOCK=$(find_block "system")
PRODUCT_BLOCK=$(find_block "product")
SYSTEM_EXT_BLOCK=$(find_block "system_ext")

if [ "$DYNAMIC_PARTITIONS" = "true" ]; then
  [ -n "$SYSTEM_BLOCK" ] && blockdev --setrw "$SYSTEM_BLOCK" 2>/dev/null || true
  [ -n "$PRODUCT_BLOCK" ] && blockdev --setrw "$PRODUCT_BLOCK" 2>/dev/null || true
  [ -n "$SYSTEM_EXT_BLOCK" ] && blockdev --setrw "$SYSTEM_EXT_BLOCK" 2>/dev/null || true
fi

SYSTEM_MNT="/mnt/system"
mkdir -p "$SYSTEM_MNT" 2>/dev/null || true

if [ -n "$SYSTEM_BLOCK" ] && mount -o rw "$SYSTEM_BLOCK" "$SYSTEM_MNT" 2>/dev/null; then
  ui_print "[✓] Mounted $SYSTEM_MNT"
elif mount -o rw /system 2>/dev/null; then
  SYSTEM_MNT="/system"
  ui_print "[✓] Mounted /system"
elif mount -o rw /system_root 2>/dev/null; then
  SYSTEM_MNT="/system_root"
  ui_print "[✓] Mounted /system_root"
fi

if [ -d "$SYSTEM_MNT/system" ]; then
  SYSTEM_OUT="$SYSTEM_MNT/system"
else
  SYSTEM_OUT="$SYSTEM_MNT"
fi

ui_print "[*] Target System Root: $SYSTEM_OUT"

if [ -L "${SYSTEM_MNT}/product" ] || [ -L "${SYSTEM_OUT}/product" ]; then
  PRODUCT_BLOCK=""
fi
if [ -L "${SYSTEM_MNT}/system_ext" ] || [ -L "${SYSTEM_OUT}/system_ext" ]; then
  SYSTEM_EXT_BLOCK=""
fi

if [ -n "$PRODUCT_BLOCK" ]; then
  mkdir -p /product 2>/dev/null || true
  mount -o rw "$PRODUCT_BLOCK" /product 2>/dev/null && ui_print "[✓] /product mounted" || PRODUCT_BLOCK=""
fi

if [ -n "$SYSTEM_EXT_BLOCK" ]; then
  mkdir -p /system_ext 2>/dev/null || true
  mount -o rw "$SYSTEM_EXT_BLOCK" /system_ext 2>/dev/null && ui_print "[✓] /system_ext mounted" || SYSTEM_EXT_BLOCK=""
fi

cd "$TMP/system" 2>/dev/null || cd "$TMP"

ui_print "[*] Generating dynamic addon.d survival script..."
if [ -f addon.d/addond_head ] && [ -f addon.d/addond_tail ]; then
  cat addon.d/addond_head > addon.d/70-gapps.sh
  for f in $(find . ! -path "./addon.d/*" -type f); do
    line=$(echo "$f" | sed 's/^\.\///')
    echo "$line" >> addon.d/70-gapps.sh
  done
  cat addon.d/addond_tail >> addon.d/70-gapps.sh
  rm -f addon.d/addond_head addon.d/addond_tail
fi

ui_print "[*] Copying Pure GApps files to system..."
cp -a ./* "$SYSTEM_OUT/" 2>/dev/null || cp -rf ./* "$SYSTEM_OUT/" 2>/dev/null || true

if [ -n "$PRODUCT_BLOCK" ] && [ -d "./product" ]; then
  cp -a ./product/* /product/ 2>/dev/null || true
fi
if [ -n "$SYSTEM_EXT_BLOCK" ] && [ -d "./system_ext" ]; then
  cp -a ./system_ext/* /system_ext/ 2>/dev/null || true
fi

if [ -e "${SYSTEM_OUT}/system_ext/priv-app/SetupWizard" ] || [ -e "${SYSTEM_OUT}/priv-app/SetupWizard" ]; then
  rm -rf "${SYSTEM_OUT}/priv-app/Provision" 2>/dev/null || true
  rm -rf "${SYSTEM_OUT}/system_ext/priv-app/Provision" 2>/dev/null || true
fi

ui_print "[*] Setting file permissions and SELinux contexts..."
for d in $(find "$SYSTEM_OUT" -type d 2>/dev/null); do
  set_perm 0755 "$d"
  set_owner 0 0 "$d"
done

for f in $(find "$SYSTEM_OUT" -type f 2>/dev/null); do
  ext="${f##*.}"
  if [ "$ext" = "sh" ] || [ -x "$f" ]; then
    set_perm 0755 "$f"
  else
    set_perm 0644 "$f"
  fi
  set_owner 0 0 "$f"
  set_con system_file "$f"
done

if [ -d "$SYSTEM_OUT/addon.d" ]; then
  set_perm 0755 "$SYSTEM_OUT/addon.d"
  [ -f "$SYSTEM_OUT/addon.d/70-gapps.sh" ] && set_perm 0755 "$SYSTEM_OUT/addon.d/70-gapps.sh"
fi

ui_print "[*] Cleaning up temporary files..."
cd /
rm -rf "$TMP"
umount -l "$SYSTEM_MNT" 2>/dev/null || true
umount -l /product 2>/dev/null || true
umount -l /system_ext 2>/dev/null || true

ui_print "[✓] Pure Google GApps Installation Complete!"
ui_print "*****************************************"
exit 0
"""

ADDOND_HEAD = """#!/sbin/sh
#
# ADDOND_VERSION=3
#
# /system/addon.d/70-gapps.sh
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
    chmod 755 "$S/addon.d/70-gapps.sh" 2>/dev/null || true
  ;;
esac
"""

