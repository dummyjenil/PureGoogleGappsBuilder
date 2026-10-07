"""
Build-time patch script for Android 12.1.0.
Materializes the Android 12.1.0 static asset tree from canonical `res/` files.
"""

from . import copy_res, copy_latinime_so, patch_text_file, write_text_file


def apply(out_dir: str):
    copy_res('lib/arm/libsketchology_native.so', out_dir, 'arm/proprietary/product/app/MarkupGoogle/lib/arm/libsketchology_native.so')
    copy_latinime_so('lib/arm/libjni_latinimegoogle.so', out_dir, 'arm/proprietary/product/lib/libjni_latinimegoogle.so', android_14_plus=False)
    copy_res('lib/arm64/libsketchology_native.so', out_dir, 'arm64/proprietary/product/app/MarkupGoogle/lib/arm64/libsketchology_native.so')
    copy_latinime_so('lib/arm/libjni_latinimegoogle.so', out_dir, 'arm64/proprietary/product/lib/libjni_latinimegoogle.so', android_14_plus=False)
    copy_latinime_so('lib/arm64/libjni_latinimegoogle.so', out_dir, 'arm64/proprietary/product/lib64/libjni_latinimegoogle.so', android_14_plus=False)
    patch_text_file('etc/default-permissions/default-permissions-google.xml', out_dir, 'common/proprietary/product/etc/default-permissions/default-permissions-google.xml', [(30, 42, '')], executable=False)
    copy_res('etc/default-permissions/default-permissions-mtg.xml', out_dir, 'common/proprietary/product/etc/default-permissions/default-permissions-mtg.xml')
    copy_res('etc/permissions/com.google.android.dialer.support.xml', out_dir, 'common/proprietary/product/etc/permissions/com.google.android.dialer.support.xml')
    patch_text_file('etc/permissions/privapp-permissions-google-product.xml', out_dir, 'common/proprietary/product/etc/permissions/privapp-permissions-google-product.xml', [(27, 28, ''), (38, 39, ''), (84, 96, ''), (102, 103, ''), (125, 126, ''), (140, 141, ''), (149, 150, ''), (154, 170, ''), (181, 181, '    <privapp-permissions package="com.google.android.feedback">\n        <permission name="android.permission.PACKAGE_USAGE_STATS"/>\n        <permission name="android.permission.READ_LOGS"/>\n    </privapp-permissions>\n'), (182, 183, ''), (185, 186, ''), (187, 188, ''), (212, 213, ''), (216, 218, ''), (225, 227, ''), (228, 229, ''), (253, 255, ''), (258, 259, ''), (275, 301, '        <permission name="com.android.voicemail.permission.READ_VOICEMAIL"/>\n'), (324, 326, ''), (360, 361, ''), (362, 362, '        <permission name="android.permission.BIND_DIRECTORY_SEARCH"/>\n'), (374, 376, '        <permission name="android.permission.START_ACTIVITIES_FROM_BACKGROUND"/>\n        <permission name="android.permission.TOGGLE_AUTOMOTIVE_PROJECTION"/>\n'), (377, 377, '    </privapp-permissions>\n    <privapp-permissions package="com.google.android.syncadapters.contacts">\n        <permission name="android.permission.INTERACT_ACROSS_USERS"/>\n')], executable=False)
    copy_res('security/fsverity/gms_fsverity_cert.der', out_dir, 'common/proprietary/product/etc/security/fsverity/gms_fsverity_cert.der')
    copy_res('etc/sysconfig/d2d_cable_migration_feature.xml', out_dir, 'common/proprietary/product/etc/sysconfig/d2d_cable_migration_feature.xml')
    copy_res('etc/sysconfig/google-hiddenapi-package-allowlist.xml', out_dir, 'common/proprietary/product/etc/sysconfig/google-hiddenapi-package-allowlist.xml')
    patch_text_file('etc/sysconfig/google.xml', out_dir, 'common/proprietary/product/etc/sysconfig/google.xml', [(12, 15, ''), (32, 35, '    <!-- If CarrierServices is installed, it must always have network access to\n         reliably receive IMS messages. -->\n    <allow-in-power-save package="com.google.android.ims" />\n    <allow-in-data-usage-save package="com.google.android.ims" />\n'), (63, 85, ''), (92, 98, '')], executable=False)
    copy_res('etc/sysconfig/google_build.xml', out_dir, 'common/proprietary/product/etc/sysconfig/google_build.xml')
    copy_res('framework/com.google.android.dialer.support.jar', out_dir, 'common/proprietary/product/framework/com.google.android.dialer.support.jar')
    patch_text_file('etc/permissions/privapp-permissions-google-system-ext.xml', out_dir, 'common/proprietary/system_ext/etc/permissions/privapp-permissions-google-system-ext.xml', [(6, 13, ''), (14, 14, '        <permission name="android.permission.READ_LOGS"/>\n'), (15, 17, ''), (65, 66, '')], executable=False)
    patch_text_file('overlay/GmsOverlay/AndroidManifest.xml', out_dir, 'overlay/GmsOverlay/AndroidManifest.xml', [(4, 5, '')], executable=False)
    patch_text_file('overlay/GmsOverlay/res/values/config.xml', out_dir, 'overlay/GmsOverlay/res/values/config.xml', [(2, 5, ''), (47, 49, ''), (59, 77, '')], executable=False)
    patch_text_file('overlay/GmsSettingsProviderOverlay/AndroidManifest.xml', out_dir, 'overlay/GmsSettingsProviderOverlay/AndroidManifest.xml', [(4, 5, '')], executable=False)
    copy_res('overlay/GmsSettingsProviderOverlay/res/values/defaults.xml', out_dir, 'overlay/GmsSettingsProviderOverlay/res/values/defaults.xml')
    patch_text_file('proprietary-files/proprietary-files-arm-nongrouper.txt', out_dir, 'proprietary-files-arm-nongrouper.txt', [(0, 3, '-product/app/MarkupGoogle/MarkupGoogle.apk;PRESIGNED|012bf4c0622d9d0aa4361a62e7ce07a1eb056b8f\n-product/app/SpeechServicesByGoogle/SpeechServicesByGoogle.apk;PRESIGNED\n-product/app/talkback/talkback.apk;PRESIGNED\n-product/priv-app/Velvet/Velvet.apk;PRESIGNED\nproduct/app/MarkupGoogle/lib/arm/libsketchology_native.so|479720ba394500786e5b5a39deb09a93d5bce9db\n'), (4, 5, '-system_ext/priv-app/SetupWizard/SetupWizard.apk;OVERRIDES=Provision;PRESIGNED\n')], executable=False)
    copy_res('proprietary-files/proprietary-files-arm.txt', out_dir, 'proprietary-files-arm.txt')
    patch_text_file('proprietary-files/proprietary-files-arm64-nongrouper.txt', out_dir, 'proprietary-files-arm64-nongrouper.txt', [(0, 1, '-product/app/MarkupGoogle/MarkupGoogle.apk;PRESIGNED|012bf4c0622d9d0aa4361a62e7ce07a1eb056b8f\n'), (4, 5, 'product/app/MarkupGoogle/lib/arm64/libsketchology_native.so|5c55b4d32beeeca04b4e9f4ce1a2cd3e15a32c8c\n')], executable=False)
    copy_res('proprietary-files/proprietary-files-arm64.txt', out_dir, 'proprietary-files-arm64.txt')
    patch_text_file('proprietary-files/proprietary-files-common-nongrouper.txt', out_dir, 'proprietary-files-common-nongrouper.txt', [(0, 4, '-product/priv-app/GoogleRestore/GoogleRestore.apk;PRESIGNED\n')], executable=False)
    patch_text_file('proprietary-files/proprietary-files-common.txt', out_dir, 'proprietary-files-common.txt', [(1, 2, '-product/app/GoogleContactsSyncAdapter/GoogleContactsSyncAdapter.apk;PRESIGNED\n'), (11, 13, '')], executable=False)
    copy_res('proprietary-files/proprietary-files-x86-nongrouper.txt', out_dir, 'proprietary-files-x86-nongrouper.txt')
    copy_res('proprietary-files/proprietary-files-x86.txt', out_dir, 'proprietary-files-x86.txt')
    patch_text_file('proprietary-files/proprietary-files-x86_64-nongrouper.txt', out_dir, 'proprietary-files-x86_64-nongrouper.txt', [(0, 1, '-product/priv-app/Velvet/Velvet.apk;PRESIGNED\n'), (2, 3, '-system_ext/priv-app/SetupWizard/SetupWizard.apk;OVERRIDES=Provision;PRESIGNED\n')], executable=False)
    copy_res('proprietary-files/proprietary-files-x86_64.txt', out_dir, 'proprietary-files-x86_64.txt')
    patch_text_file('update-binary', out_dir, 'update-binary', [(25, 25, '}\n\nnice_arch() {\n  case $1 in\n    aarch64*|armv8*)\n      echo "arm64"\n      ;;\n    arm*)\n      echo "arm"\n      ;;\n    *)\n      echo $1\n      ;;\n  esac\n'), (109, 111, '  rm -rf product/app/MarkupGoogle\n'), (114, 116, ''), (133, 134, 'CPU_ARCH=$(uname -m)\n'), (135, 136, '  error "This package is built for $(nice_arch $GAPPS_ARCH) but your device is $(nice_arch $CPU_ARCH)! Aborting"\n'), (246, 256, '')], executable=True)
    copy_latinime_so('lib/x86/libjni_latinimegoogle.so', out_dir, 'x86/proprietary/product/lib/libjni_latinimegoogle.so', android_14_plus=False)
    copy_latinime_so('lib/x86/libjni_latinimegoogle.so', out_dir, 'x86_64/proprietary/product/lib/libjni_latinimegoogle.so', android_14_plus=False)
    copy_latinime_so('lib/x86_64/libjni_latinimegoogle.so', out_dir, 'x86_64/proprietary/product/lib64/libjni_latinimegoogle.so', android_14_plus=False)
