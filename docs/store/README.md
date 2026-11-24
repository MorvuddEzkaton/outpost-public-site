# Offline English Lite Store listing preparation

For OutPOSt Lite only (9N5K4B1229VC), MSI/EXE listing CSV. This is not an installer submission or a live Store update. First confirm the package type in Partner Center; MSIX uses a different field schema.

Microsoft documentation:
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/import-and-export-store-listings
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/create-app-submission
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/support-info

1. Open the existing Lite submission and add English (United States) in Manage Store listings, if not already present. Export a fresh CSV with all selected languages; keep the original private and backed up.
2. Run the offline self-test: `python scripts/prepare_lite_store_listing.py --self-test`.
3. Run `python scripts/prepare_lite_store_listing.py --product-id 9N5K4B1229VC --input exported.csv --output lite-en-draft.csv`. The export must already contain the exact existing OutPOSt Lite product name and the en-US column. The ID is an explicit operator assertion, not independently authenticated by CSV.
4. Existing nonempty English text is refused by default. Review it before explicitly using `--allow-replace`. No other language, name, license terms, release notes, image paths or package settings are edited. CSV encoding/BOM and logical cell values are preserved; serialization may change line endings/quoting. Empty English name remains empty; complete any required fields manually.
5. Compare all cells before import. Use real screenshots from the English Store build and verify the complete current feature scope. A real fresh export and Windows Store package acceptance remain required; synthetic test data is not a submit-ready export.
6. Before first import, confirm every selected language has a nonempty Description and Applicable license terms, plus real files at Screenshots1 and StoreLogos1 (relative paths). Microsoft requires a folder containing exactly one CSV and all referenced assets for first import; place the reviewed draft and assets in a separate staging folder, not beside the original CSV. Do not invent missing terms or screenshots. Import the reviewed draft into Partner Center; inspect validation errors, package requirements, selected languages, screenshot and license fields. Do not submit until actual content and listing scope are accepted. Support/privacy/website are separate product properties and not changed by the tool. The Store privacy policy applies to all published markets: use a reviewed bilingual policy link only after both pages are accepted on production. No international regulatory compliance claim.

The structured manifest contains 17 text fields (description, short description, 8 features, 7 terms), based on #152. Deliberately excludes URLs from description, pricing changes, product title edits, screenshots and What's New. No access token, API calls, paid browser, or automatic submission. Keep exports out of the public repository.
