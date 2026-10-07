"""
Build-time patch script for Android 13.0.0.
Materializes the Android 13.0.0 static asset tree from canonical `res/` files.
"""

from . import copy_res, copy_latinime_so, patch_text_file, write_text_file


def apply(out_dir: str):
    copy_latinime_so('lib/arm/libjni_latinimegoogle.so', out_dir, 'arm/proprietary/product/lib/libjni_latinimegoogle.so', android_14_plus=False)
    copy_latinime_so('lib/arm/libjni_latinimegoogle.so', out_dir, 'arm64/proprietary/product/lib/libjni_latinimegoogle.so', android_14_plus=False)
    copy_latinime_so('lib/arm64/libjni_latinimegoogle.so', out_dir, 'arm64/proprietary/product/lib64/libjni_latinimegoogle.so', android_14_plus=False)
    copy_res('etc/default-permissions/default-permissions-google.xml', out_dir, 'common/proprietary/product/etc/default-permissions/default-permissions-google.xml')
    copy_res('etc/default-permissions/default-permissions-mtg.xml', out_dir, 'common/proprietary/product/etc/default-permissions/default-permissions-mtg.xml')
    copy_res('etc/init/gapps.rc', out_dir, 'common/proprietary/product/etc/init/gapps.rc')
    copy_res('etc/permissions/com.google.android.dialer.support.xml', out_dir, 'common/proprietary/product/etc/permissions/com.google.android.dialer.support.xml')
    copy_res('etc/permissions/privapp-permissions-google-product.xml', out_dir, 'common/proprietary/product/etc/permissions/privapp-permissions-google-product.xml')
    copy_res('security/fsverity/gms_fsverity_cert.der', out_dir, 'common/proprietary/product/etc/security/fsverity/gms_fsverity_cert.der')
    copy_res('etc/sysconfig/d2d_cable_migration_feature.xml', out_dir, 'common/proprietary/product/etc/sysconfig/d2d_cable_migration_feature.xml')
    copy_res('etc/sysconfig/google-hiddenapi-package-allowlist.xml', out_dir, 'common/proprietary/product/etc/sysconfig/google-hiddenapi-package-allowlist.xml')
    patch_text_file('etc/sysconfig/google.xml', out_dir, 'common/proprietary/product/etc/sysconfig/google.xml', [(12, 15, ''), (32, 35, '    <!-- If CarrierServices is installed, it must always have network access to\n         reliably receive IMS messages. -->\n    <allow-in-power-save package="com.google.android.ims" />\n    <allow-in-data-usage-save package="com.google.android.ims" />\n'), (63, 85, ''), (93, 98, '    <!-- Restrict ASI and Private Compute Services -->\n    <allow-association target="com.google.android.as" allowed="com.android.bluetooth" />\n    <allow-association target="com.google.android.as" allowed="com.android.providers.contacts" />\n    <allow-association target="com.google.android.as" allowed="com.android.providers.media" />\n    <allow-association target="com.google.android.as" allowed="com.android.providers.telephony" />\n    <allow-association target="com.google.android.as" allowed="com.android.systemui" />\n    <allow-association target="com.google.android.as" allowed="com.google.android.providers.media.module" />\n    <allow-association target="com.google.android.as" allowed="com.google.android.as.oss" />\n    <allow-association target="com.google.android.as" allowed="com.google.android.bluetooth.services" />\n    <allow-association target="com.google.android.as.oss" allowed="com.google.android.as" />\n')], executable=False)
    copy_res('etc/sysconfig/google_build.xml', out_dir, 'common/proprietary/product/etc/sysconfig/google_build.xml')
    copy_res('framework/com.google.android.dialer.support.jar', out_dir, 'common/proprietary/product/framework/com.google.android.dialer.support.jar')
    copy_res('etc/permissions/privapp-permissions-google-system-ext.xml', out_dir, 'common/proprietary/system_ext/etc/permissions/privapp-permissions-google-system-ext.xml')
    copy_res('overlay/GmsOverlay/AndroidManifest.xml', out_dir, 'overlay/GmsOverlay/AndroidManifest.xml')
    copy_res('overlay/GmsOverlay/res/values/config.xml', out_dir, 'overlay/GmsOverlay/res/values/config.xml')
    copy_res('overlay/GmsSettingsProviderOverlay/AndroidManifest.xml', out_dir, 'overlay/GmsSettingsProviderOverlay/AndroidManifest.xml')
    copy_res('overlay/GmsSettingsProviderOverlay/res/values/defaults.xml', out_dir, 'overlay/GmsSettingsProviderOverlay/res/values/defaults.xml')
    patch_text_file('proprietary-files/proprietary-files-arm-nongrouper.txt', out_dir, 'proprietary-files-arm-nongrouper.txt', [(0, 3, '-product/app/SpeechServicesByGoogle/SpeechServicesByGoogle.apk;PRESIGNED\n-product/app/talkback/talkback.apk;PRESIGNED\n-product/priv-app/Velvet/Velvet.apk;PRESIGNED\n'), (4, 5, '-system_ext/priv-app/SetupWizard/SetupWizard.apk;OVERRIDES=Provision;PRESIGNED\n')], executable=False)
    copy_res('proprietary-files/proprietary-files-arm.txt', out_dir, 'proprietary-files-arm.txt')
    copy_res('proprietary-files/proprietary-files-arm64-nongrouper.txt', out_dir, 'proprietary-files-arm64-nongrouper.txt')
    copy_res('proprietary-files/proprietary-files-arm64.txt', out_dir, 'proprietary-files-arm64.txt')
    patch_text_file('proprietary-files/proprietary-files-common-nongrouper.txt', out_dir, 'proprietary-files-common-nongrouper.txt', [(0, 4, '-product/priv-app/GoogleRestore/GoogleRestore.apk;PRESIGNED\n')], executable=False)
    copy_res('proprietary-files/proprietary-files-common.txt', out_dir, 'proprietary-files-common.txt')
    copy_res('proprietary-files/proprietary-files-x86-nongrouper.txt', out_dir, 'proprietary-files-x86-nongrouper.txt')
    copy_res('proprietary-files/proprietary-files-x86.txt', out_dir, 'proprietary-files-x86.txt')
    patch_text_file('proprietary-files/proprietary-files-x86_64-nongrouper.txt', out_dir, 'proprietary-files-x86_64-nongrouper.txt', [(0, 1, '-product/priv-app/Velvet/Velvet.apk;PRESIGNED\n'), (2, 3, '-system_ext/priv-app/SetupWizard/SetupWizard.apk;OVERRIDES=Provision;PRESIGNED\n')], executable=False)
    copy_res('proprietary-files/proprietary-files-x86_64.txt', out_dir, 'proprietary-files-x86_64.txt')
    patch_text_file('update-binary', out_dir, 'update-binary', [(109, 110, '  rm -rf product/app/MarkupGoogle\n'), (115, 116, '')], executable=True)
    copy_latinime_so('lib/x86/libjni_latinimegoogle.so', out_dir, 'x86/proprietary/product/lib/libjni_latinimegoogle.so', android_14_plus=False)
    copy_latinime_so('lib/x86/libjni_latinimegoogle.so', out_dir, 'x86_64/proprietary/product/lib/libjni_latinimegoogle.so', android_14_plus=False)
    copy_latinime_so('lib/x86_64/libjni_latinimegoogle.so', out_dir, 'x86_64/proprietary/product/lib64/libjni_latinimegoogle.so', android_14_plus=False)
