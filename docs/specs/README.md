# Protocol specifications

Arcam's official RS-232 / IP control protocol PDFs, converted to Markdown by `nix run '.#fetch-specs'`. The spec PDFs are the first source of ground truth for the library implemention (modulo errors discovered in the specs.) These markdown versions are easier for LLM agents to consume than the original PDFs. Please regenerate them whenever the upstream PDFs change.

Caveat: `pymupdf4llm` does not always preserve table ordering — command-reference tables may appear separated from the prose that describes them. When in doubt, consult the original PDF.

## Documents

- AVR5/AVR10/AVR20/AVR30/AV40/AVR11/AVR21/AVR31/AV41 — [RS232_5_10_20_30_40_11_21_31_41__SH289E_F_07Oct21.md](RS232_5_10_20_30_40_11_21_31_41__SH289E_F_07Oct21.md) ([original PDF](https://www.arcam.co.uk/ugc/tor/AVR11/Custom%20Installation%20Notes/RS232_5_10_20_30_40_11_21_31_41__SH289E_F_07Oct21.pdf))
- SA30 — [SH306E_RS232_SA30_4.md](SH306E_RS232_SA30_4.md) ([original PDF](https://www.arcam.co.uk/ugc/tor/SA30/Custom%20Installation%20Notes/SH306E_RS232_SA30_4.pdf))
- SA750 — [SH320E_RS232_SA750_iss1.md](SH320E_RS232_SA750_iss1.md) ([original PDF](https://www.jbl.com/on/demandware.static/-/Sites-masterCatalog_Harman/default/dwabc088c9/pdfs/SH320E_RS232_SA750_iss1.pdf))
- PA720/PA240/PA410 — [RS232_PA720_PA240_PA410_SH305E_3.md](RS232_PA720_PA240_PA410_SH305E_3.md) ([original PDF](https://www.arcam.co.uk/ugc/tor/PA240/Custom%20Installation%20Notes/RS232_PA720_PA240_PA410_SH305E_3.pdf))
- ST60 — [SH309_RS232_ST60_C.md](SH309_RS232_ST60_C.md) ([original PDF](https://www.arcam.co.uk/ugc/tor/ST60/Custom%20Installation%20Notes/SH309_RS232_ST60_C.pdf))
- AV860/AVR850/AVR550/AVR390/SR250 — [RS232_860_850_550_390_250_SH274E_D_181018.md](RS232_860_850_550_390_250_SH274E_D_181018.md) ([original PDF](https://www.arcam.co.uk/ugc/tor/avr390/RS232/RS232_860_850_550_390_250_SH274E_D_181018.pdf))
- SA10/SA20 — [SH277E_RS232_SA10_SA20_B.md](SH277E_RS232_SA10_SA20_B.md) ([original PDF](https://www.arcam.co.uk/ugc/tor/SA20/Custom%20Installation%20Notes/SH277E_RS232_SA10_SA20_B.pdf))
- AVR750/AVR450/AVR380 — [RS232_AVR750450380_SH256E_3.md](RS232_AVR750450380_SH256E_3.md) ([original PDF](https://www.arcam.co.uk/ugc/tor/avr380/RS232/RS232_AVR750450380_SH256E_3.pdf))
