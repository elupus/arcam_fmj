{
  description = "Arcam FMJ receiver control library";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        inherit (pkgs) lib;

        # Each entry: { models, url, hash }
        #   models — human-readable list of receiver/amp models the spec covers, used in the generated README.
        specSources = [
          {
            models = "AVR5/AVR10/AVR20/AVR30/AV40/AVR11/AVR21/AVR31/AV41";
            url = "https://www.arcam.co.uk/ugc/tor/AVR11/Custom%20Installation%20Notes/RS232_5_10_20_30_40_11_21_31_41__SH289E_F_07Oct21.pdf";
            hash = "sha256-SJZpSAMAuDe2soJAqB8djlnags1QLnEpxIvi4OYNkOI=";
          }
          {
            models = "SA30";
            url = "https://www.arcam.co.uk/ugc/tor/SA30/Custom%20Installation%20Notes/SH306E_RS232_SA30_4.pdf";
            hash = "sha256-o6YJ1N0v914DQEAtS6ibbDJQDsUFE0VzZmbqYLk7AZo=";
          }
          {
            models = "SA750";
            url = "https://www.jbl.com/on/demandware.static/-/Sites-masterCatalog_Harman/default/dwabc088c9/pdfs/SH320E_RS232_SA750_iss1.pdf";
            hash = "sha256-cAvTiaRVf0L8GeAGwXwa811fjD9ySrOl8lu6s5u8WPY=";
          }
          {
            models = "PA720/PA240/PA410";
            url = "https://www.arcam.co.uk/ugc/tor/PA240/Custom%20Installation%20Notes/RS232_PA720_PA240_PA410_SH305E_3.pdf";
            hash = "sha256-EM/u8ECteRMIRTf2By4SmCaVUkR+sfQjI/xzS+ZtP74=";
          }
          {
            models = "ST60";
            url = "https://www.arcam.co.uk/ugc/tor/ST60/Custom%20Installation%20Notes/SH309_RS232_ST60_C.pdf";
            hash = "sha256-4BJFb/EoFsQqwxQfWKWXZMuwuhT97k7jA53uxPAJ3Dw=";
          }
          {
            models = "AV860/AVR850/AVR550/AVR390/SR250";
            url = "https://www.arcam.co.uk/ugc/tor/avr390/RS232/RS232_860_850_550_390_250_SH274E_D_181018.pdf";
            hash = "sha256-rmOBTVZS/kBkNtqEkc0ecstK+cEvL7qtV9nmNAwMwp8=";
          }
          {
            models = "SA10/SA20";
            url = "https://www.arcam.co.uk/ugc/tor/SA20/Custom%20Installation%20Notes/SH277E_RS232_SA10_SA20_B.pdf";
            hash = "sha256-KNlltjQnG/htrCTTm2x1aRo8fESCU+O3jYGlEYTZdnc=";
          }
          {
            models = "AVR750/AVR450/AVR380";
            url = "https://www.arcam.co.uk/ugc/tor/avr380/RS232/RS232_AVR750450380_SH256E_3.pdf";
            hash = "sha256-9VS6BDNTWwzVzRYGZGbyoALiT4mZMSV/DThmOldV3aE=";
          }
        ];

        specs =
          let
            withPdf = src: src // { pdf = pkgs.fetchurl { inherit (src) url hash; }; };
            withMarkdown =
              src:
              src
              // {
                markdown =
                  let
                    baseName = lib.removeSuffix ".pdf" src.pdf.name;
                  in
                  pkgs.runCommand "${baseName}.md"
                    {
                      nativeBuildInputs = [
                        (pkgs.python3.withPackages (ps: [ ps.pymupdf4llm ]))
                      ];
                      inherit (src) pdf;
                    }
                    ''
                      python3 <<'EOF'
                      import os
                      import pymupdf4llm
                      md = pymupdf4llm.to_markdown(os.environ["pdf"])
                      with open(os.environ["out"], "w") as f:
                          f.write(md)
                      EOF
                    '';
              };
            entries = map (src: withMarkdown (withPdf src)) specSources;
            readme = pkgs.writeText "README.md" ''
              # Protocol specifications

              Arcam's official RS-232 / IP control protocol PDFs, converted to Markdown by `nix run '.#fetch-specs'`. The spec PDFs are the first source of ground truth for the library implemention (modulo errors discovered in the specs.) These markdown versions are easier for LLM agents to consume than the original PDFs. Please regenerate them whenever the upstream PDFs change.

              Caveat: `pymupdf4llm` does not always preserve table ordering — command-reference tables may appear separated from the prose that describes them. When in doubt, consult the original PDF.

              ## Documents

              ${lib.concatMapStringsSep "\n" (e: "- ${e.models} — [${e.markdown.name}](${e.markdown.name}) ([original PDF](${e.url}))") entries}
            '';
          in
          pkgs.runCommand "arcam-specs" { } ''
            mkdir -p $out
            ln -s ${readme} $out/README.md
            ${lib.concatMapStringsSep "\n" (e: "ln -s ${e.markdown} $out/${e.markdown.name}") entries}
          '';

        fetch-specs = pkgs.writeShellApplication {
          name = "fetch-specs";
          runtimeInputs = [ pkgs.coreutils ];
          # Replace existing *.md and README.md in docs/specs; leave any other
          # files (e.g. hand-written notes) alone.
          text = ''
            dest=docs/specs
            mkdir -p "$dest"
            rm -f "$dest"/*.md
            cp -L --no-preserve=mode ${specs}/*.md "$dest"/
          '';
        };

        firmwareZip = pkgs.fetchurl {
          url = "https://www.arcam.co.uk/ugc/tor/AV41/v1.62%202148%20Unit%20Software/AVRx1_1v62_2148.zip";
          hash = "sha256-5wCU0N4mKYd9/Bl4/JAX5Qk2QBYWzf6koOPgNZrmq/E=";
        };

        firmwareUnzipped =
          pkgs.runCommand "AVRx1_1v62_2148"
            {
              nativeBuildInputs = [ pkgs.unzip ];
            }
            ''
              unzip ${firmwareZip} -d $out
            '';

        # SWUpdate payload for the Amlogic A113D Linux SoC (network/streaming side).
        firmwareNetRaw =
          pkgs.runCommand "AVRx1_1v62_2148-net-raw"
            {
              nativeBuildInputs = [ pkgs.cpio ];
            }
            ''
              mkdir -p $out
              cd $out
              cpio -idv < ${firmwareUnzipped}/image.swu
            '';

        # Yocto rootfs — the .ubifs blob is XZ-compressed (see sw-description).
        firmwareNetRootfs =
          pkgs.runCommand "AVRx1_1v62_2148-net-rootfs"
            {
              nativeBuildInputs = [
                pkgs.xz
                pkgs.ubi_reader
              ];
            }
            ''
              xz -dc ${firmwareNetRaw}/yocto-nsdk-ip-image-swu-a113d-arcam.ubifs > rootfs.ubifs
              ubireader_extract_files -o "$out" rootfs.ubifs
            '';

        # Split a signed FIT image into its sub-images. Kernel/ramdisk are gzip-compressed
        # inside the FIT, so decompress them after extraction.
        extractFit =
          name: fit: subimages:
          pkgs.runCommand name
            {
              nativeBuildInputs = [
                pkgs.ubootTools
                pkgs.gzip
                pkgs.cpio
              ];
            }
            ''
              mkdir -p $out
              ${lib.concatMapStringsSep "\n" (s: ''
                dumpimage -T flat_dt -p ${toString s.index} -o "$out/${s.name}${s.ext or ""}" ${fit}
                ${lib.optionalString (s.gunzip or false) ''
                  gunzip "$out/${s.name}${s.ext or ""}"
                ''}
                ${lib.optionalString (s.cpio or false) ''
                  mkdir -p "$out/${s.name}.d"
                  ( cd "$out/${s.name}.d" && cpio -idmv < "$out/${s.name}" )
                ''}
              '') subimages}
            '';

        firmwareNetFit =
          extractFit "AVRx1_1v62_2148-net-fit" "${firmwareNetRaw}/fitImage-a113d-arcam-signed"
            [
              {
                index = 0;
                name = "kernel";
                ext = ".gz";
                gunzip = true;
              }
              {
                index = 1;
                name = "fdt.dtb";
              }
            ];

        firmwareNetFitSwu =
          extractFit "AVRx1_1v62_2148-net-fit-swu" "${firmwareNetRaw}/fitImage-swu-a113d-arcam-signed"
            [
              {
                index = 0;
                name = "kernel";
                ext = ".gz";
                gunzip = true;
              }
              {
                index = 1;
                name = "fdt.dtb";
              }
              {
                index = 2;
                name = "ramdisk.cpio";
                ext = ".gz";
                gunzip = true;
                cpio = true;
              }
            ];

        firmwareNetUboot =
          pkgs.runCommand "AVRx1_1v62_2148-net-uboot"
            {
              nativeBuildInputs = [
                pkgs.gnutar
                pkgs.gzip
              ];
            }
            ''
              mkdir -p $out
              tar -xzf ${firmwareNetRaw}/u-boot.tar.gz -C $out
            '';

        # Full demangled aarch64 disassembly of binaries plausibly involved in the TCP-bridge data path. See CLAUDE.md "TCP-serial bridge" for context.
        firmwareNetAnalysis =
          let
            disasmTargets = [
              # Binaries
              "usr/share/nsdk/nSDK"
              "usr/bin/hostlink_cli"
              "usr/bin/nsdk_cli"
              # Directly involved
              "usr/lib64/libnsdk_hostLink.so"
              "usr/lib64/libnsdk_hostLinkLib.so"
              "usr/lib64/libnsdk_serialComm.so"
              "usr/lib64/libnsdk_thrift_api.so"
              "usr/lib64/libnsdk_api.so"
              # Could intercept / wrap the data path or hold relevant state
              "usr/lib64/libnsdk_networking.so"
              "usr/lib64/libnsdk_services.so"
              "usr/lib64/libnsdk_simple_ipc.so"
              "usr/lib64/libnsdk_webserver.so"
              "usr/lib64/libnsdk_machine.so"
              "usr/lib64/libnsdk_systemManager.so"
              "usr/lib64/libnsdk_processhandler.so"
              "usr/lib64/libnsdk_powerHandler.so"
              "usr/lib64/libnsdk_powerManager.so"
              # Settings/infra used by hostlink
              "usr/lib64/libnsdk_constpartition.so"
              "usr/lib64/libnsdk_sysfs.so"
              "usr/lib64/libnsdk_mLib.so"
              "usr/lib64/libnsdk_miscUtils.so"
              # mDNS — registers the port-50000 advert; may surface session lifecycle
              "usr/lib64/libnsdk_mdnsHelpers.so"
              "usr/lib64/libnsdk_mdnsSystemMembers.so"
            ];
          in
          pkgs.runCommand "AVRx1_1v62_2148-net-analysis"
            {
              nativeBuildInputs = [ pkgs.llvm ];
            }
            ''
              mkdir -p $out/disasm
              ${lib.concatMapStringsSep "\n" (t: ''
                llvm-objdump --disassemble --demangle ${firmwareNetRootfs}/${t} \
                  > $out/disasm/${baseNameOf t}.S
              '') disasmTargets}
            '';

        firmwareNet = pkgs.runCommand "AVRx1_1v62_2148-net" { } ''
          mkdir -p $out
          cp -r --no-preserve=mode ${firmwareNetRootfs}   $out/rootfs
          cp -r --no-preserve=mode ${firmwareNetFit}      $out/fit
          cp -r --no-preserve=mode ${firmwareNetFitSwu}   $out/fit-swu
          cp -r --no-preserve=mode ${firmwareNetUboot}    $out/u-boot
          cp -r --no-preserve=mode ${firmwareNetAnalysis} $out/analysis
          for f in ${firmwareNetRaw}/*; do
            cp -L --no-preserve=mode "$f" "$out/$(basename "$f")"
          done
        '';

        # Extract the two STM32 code regions from the host firmware bundle and
        # disassemble each in Thumb-2. Section boundaries inside the 90 MB .fw blob
        # (mostly 0xFF padding) were determined by inspecting the vector-table
        # patterns at the start of each contiguous run of non-0xFF bytes.
        #
        #   file offset  flash addr   contents
        #   0x000000     0x08000000   STM32 update bootloader (~60 KB)
        #   0x010000     0x08010000   STM32 main app (~872 KB)
        #
        # The remainder of the .fw is TI Performance Audio DSP firmware + the
        # "Bach" audio sub-component, which are not relevant to the protocol
        # path we analyse and so are not disassembled here.
        firmwareHostAnalysis =
          let
            # (region name, file-offset start, file-offset end exclusive, flash load addr)
            regions = [
              { name = "stm32_bootloader"; src = "0x0"; dst = "0x10000"; vma = "0x08000000"; }
              { name = "stm32_app"; src = "0x10000"; dst = "0xea020"; vma = "0x08010000"; }
            ];
          in
          pkgs.runCommand "AVRx1_1v62_2148-host-analysis"
            {
              nativeBuildInputs = [
                pkgs.coreutils
                pkgs.gcc-arm-embedded
              ];
            }
            ''
              mkdir -p $out/extracted $out/disasm
              FW=$(echo ${firmwareUnzipped}/*.fw)
              ${lib.concatMapStringsSep "\n" (r: ''
                dd if=$FW of=$out/extracted/${r.name}.bin bs=1 \
                   skip=$(( ${r.src} )) count=$(( ${r.dst} - ${r.src} )) status=none
                arm-none-eabi-objdump -D -b binary -m armv7e-m -M force-thumb \
                  --adjust-vma=${r.vma} $out/extracted/${r.name}.bin \
                  > $out/disasm/${r.name}.S
              '') regions}
            '';

        # Core MCU firmware for the AVR receiver itself, plus extracted/disassembled
        # STM32 code regions for analysis.
        firmwareHost = pkgs.runCommand "AVRx1_1v62_2148-host" { } ''
          mkdir -p $out
          for f in ${firmwareUnzipped}/*.fw; do
            ln -s "$f" "$out/$(basename "$f")"
          done
          cp -r --no-preserve=mode ${firmwareHostAnalysis} $out/analysis
        '';

        firmware = pkgs.runCommand "arcam-firmware" { } ''
          mkdir -p $out
          cp -r --no-preserve=mode ${firmwareHost} $out/host
          cp -r --no-preserve=mode ${firmwareNet}  $out/net
          for f in ${firmwareUnzipped}/*; do
            name=$(basename "$f")
            case "$name" in
              image.swu|*.fw) ;;
              *) cp -L --no-preserve=mode "$f" "$out/$name" ;;
            esac
          done
        '';

        fetch-firmware = pkgs.writeShellApplication {
          name = "fetch-firmware";
          runtimeInputs = [ pkgs.coreutils ];
          # Plain `cp -r` (no -L) so absolute symlinks inside extracted filesystems
          # (e.g. /usr/sbin/...) are preserved rather than dereferenced against the host.
          text = ''
            rm -rf .firmware
            cp -r --no-preserve=mode ${firmware} .firmware
          '';
        };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            uv
            python3
            nixfmt
          ];

          shellHook = ''
            export UV_PYTHON_PREFERENCE=only-system
          '';
        };

        packages.specs = specs;
        packages.firmware = firmware;

        apps.fetch-specs = {
          type = "app";
          program = "${fetch-specs}/bin/fetch-specs";
        };
        apps.fetch-firmware = {
          type = "app";
          program = "${fetch-firmware}/bin/fetch-firmware";
        };
      }
    );
}
