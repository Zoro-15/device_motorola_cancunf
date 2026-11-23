import os
import re
import sys
import xml.etree.ElementTree as ET
import subprocess

# Ensure execution is always anchored to this device tree root
DEVICE_TREE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(DEVICE_TREE_DIR)

def run_check(name, fn):
    print(f"[*] Testing: {name} ...", end=" ")
    try:
        ok, msg = fn()
        if ok:
            print(f"[\033[92mPASS\033[0m] {msg}")
            return True
        else:
            print(f"[\033[91mFAIL\033[0m] {msg}")
            return False
    except Exception as e:
        print(f"[\033[91mERROR\033[0m] {str(e)}")
        return False

def check_fstab():
    fstab_path = "init/fstab.mt6855"
    if not os.path.exists(fstab_path):
        return False, f"{fstab_path} not found"
    hazard_parts = {"protect1", "protect2", "nvdata", "nvcfg", "persist", "prodpersist", "tzapp_a"}
    with open(fstab_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 5:
                dev, flags = parts[0], parts[4]
                for hp in hazard_parts:
                    if hp in dev and "formattable" in flags:
                        return False, f"Line {idx}: {hp} has 'formattable' flag!"
    return True, "No protected NVRAM/persist partitions are formattable."

def check_props():
    sys_prop = "configs/properties/system.prop"
    ven_prop = "configs/properties/vendor.prop"
    if not os.path.exists(sys_prop) or not os.path.exists(ven_prop):
        return False, "Property files missing"
    
    with open(sys_prop, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if line.startswith("vendor.") or line.startswith("persist.vendor."):
                return False, f"system.prop line {idx} contains vendor property: {line}"
    
    keys = set()
    with open(ven_prop, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k = line.split("=", 1)[0].strip()
                if k in keys:
                    return False, f"Duplicate key in vendor.prop: {k}"
                keys.add(k)
    
    if "ro.vendor.afbc.enable" not in keys:
        return False, "ro.vendor.afbc.enable missing in vendor.prop"
    return True, "Properties strictly namespaced and no duplicates."

def check_vintf_xml():
    vintf_dir = "configs/vintf"
    for fn in os.listdir(vintf_dir):
        if fn.endswith(".xml"):
            p = os.path.join(vintf_dir, fn)
            try:
                ET.parse(p)
            except Exception as e:
                return False, f"XML syntax error in {p}: {e}"
    return True, "All VINTF XML files are well-formed."

def check_copy_files():
    dev_mk = "device.mk"
    missing = []
    found_count = 0
    with open(dev_mk, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            # Ignore variable assignments and macro calls
            if ":=" in line_str or "+=" in line_str or line_str.startswith("$(call "):
                continue
            if ":" in line_str and ("$(DEVICE_PATH)/" in line_str or "device/motorola/cancunf/" in line_str):
                # Extract the source path portion before the colon target
                src_part = line_str.split(":")[0].strip()
                src_resolved = src_part.replace("$(DEVICE_PATH)/", "").replace("device/motorola/cancunf/", "").strip("\\ \t")
                if src_resolved:
                    found_count += 1
                    if not os.path.exists(src_resolved):
                        missing.append(src_resolved)
    if missing:
        return False, f"Missing copy files on disk: {missing[:3]}"
    return True, f"All device tree source copy files exist ({found_count} verified)."

def check_sepolicy():
    m_cam = "sepolicy/vendor/mtk_hal_camera.te"
    h_cam = "sepolicy/vendor/hal_camera_default.te"
    with open(m_cam, "r", encoding="utf-8") as f:
        m_txt = f.read()
    with open(h_cam, "r", encoding="utf-8") as f:
        h_txt = f.read()
    if "binder_call(mtk_hal_camera, hal_camera_default)" not in m_txt:
        return False, "mtk_hal_camera missing binder_call to hal_camera_default"
    if "binder_call(hal_camera_default, mtk_hal_camera)" not in h_txt:
        return False, "hal_camera_default missing binder_call to mtk_hal_camera"
    return True, "Camera tuner binder IPC rules present."

if __name__ == "__main__":
    print("=" * 60)
    print("  PENGUINOS CELERITY PRE-FLIGHT LIGHTWEIGHT AUDIT (CANCUNF)")
    print("=" * 60)
    results = [
        run_check("Fstab Brick Safety", check_fstab),
        run_check("Treble Property Boundaries", check_props),
        run_check("VINTF XML Validation", check_vintf_xml),
        run_check("Device Copy Files Integrity", check_copy_files),
        run_check("Camera SELinux Binder Rules", check_sepolicy),
    ]
    print("=" * 60)
    if all(results):
        print("\033[92mALL PRE-FLIGHT CHECKS PASSED. Ready for cloud build server deployment.\033[0m")
        sys.exit(0)
    else:
        print("\033[91mPRE-FLIGHT CHECKS FAILED. Correct issues before paying for server.\033[0m")
        sys.exit(1)
