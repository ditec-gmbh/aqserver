; Script generated by the HM NIS Edit Script Wizard.

; HM NIS Edit Wizard helper defines
!define PRODUCT_NAME "Aqserver"
!define PRODUCT_VERSION "1.0"
!define PRODUCT_PUBLISHER "Michael Taxis"
!define PRODUCT_WEB_SITE "http://www.taxis-instruments.de"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\aqserver.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

SetCompressor lzma

; MUI 1.67 compatible ------
!include "MUI.nsh"

; MUI Settings
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; Language Selection Dialog Settings
!define MUI_LANGDLL_REGISTRY_ROOT "${PRODUCT_UNINST_ROOT_KEY}"
!define MUI_LANGDLL_REGISTRY_KEY "${PRODUCT_UNINST_KEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "NSIS:Language"

; Welcome page
!insertmacro MUI_PAGE_WELCOME
; License page
!define MUI_LICENSEPAGE_CHECKBOX
!insertmacro MUI_PAGE_LICENSE "lgpl-3.0.txt"
; Directory page
!insertmacro MUI_PAGE_DIRECTORY
; Instfiles page
!insertmacro MUI_PAGE_INSTFILES
; Finish page
!define MUI_FINISHPAGE_RUN "$INSTDIR\aqserver.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "-c"
!define MUI_FINISHPAGE_SHOWREADME "$DOCUMENTS\Aqserver\aqserver.cfg"
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

; Language files
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"

; Reserve files
!insertmacro MUI_RESERVEFILE_INSTALLOPTIONS

; MUI end ------

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "Setup.exe"
InstallDir "$PROGRAMFILES\Aqserver"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show

Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

Section "Hauptgruppe" SEC01
  SetOutPath "$INSTDIR"
  SetOverwrite ifnewer
  File "..\dist\aqserver.exe"
  CreateDirectory "$SMPROGRAMS\Aqserver"
  CreateShortCut "$SMPROGRAMS\Aqserver\Aqserver.lnk" "$INSTDIR\aqserver.exe"
  CreateShortCut "$DESKTOP\Aqserver.lnk" "$INSTDIR\aqserver.exe"
  SetOutPath "$WINDIR\system32"
  File "..\dist\snap7.dll"
  SetOutPath "$DOCUMENTS\Aqserver"
  File "..\dist\aqserver.bat"
  File "..\dist\aqserver.cfg"
  SetOutPath "$DOCUMENTS\Aqserver\help\de"
  File "..\dist\de\aqserver.chm"
  CreateShortCut "$SMPROGRAMS\Aqserver\Help.lnk" "$DOCUMENTS\Aqserver\help\de\aqserver.chm"
  File "..\dist\de\aqserver.pdf"
  SetOutPath "$DOCUMENTS\Aqserver\help\en"
  File "..\dist\en\aqserver.chm"
  CreateShortCut "$SMPROGRAMS\Aqserver\Help.lnk" "$DOCUMENTS\Aqserver\help\en\aqserver.chm"
  File "..\dist\en\aqserver.pdf"
SectionEnd

Section -AdditionalIcons
  SetOutPath $INSTDIR
  WriteIniStr "$INSTDIR\${PRODUCT_NAME}.url" "InternetShortcut" "URL" "${PRODUCT_WEB_SITE}"
  CreateShortCut "$SMPROGRAMS\Aqserver\Website.lnk" "$INSTDIR\${PRODUCT_NAME}.url"
  CreateShortCut "$SMPROGRAMS\Aqserver\Uninstall.lnk" "$INSTDIR\uninst.exe"
SectionEnd

Section -Post
  WriteUninstaller "$INSTDIR\uninst.exe"
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\aqserver.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\aqserver.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd


Function un.onUninstSuccess
  HideWindow
  MessageBox MB_ICONINFORMATION|MB_OK "$(^Name) wurde erfolgreich deinstalliert."
FunctionEnd

Function un.onInit
!insertmacro MUI_UNGETLANGUAGE
  MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "M�chten Sie $(^Name) und alle seinen Komponenten deinstallieren?" IDYES +2
  Abort
FunctionEnd

Section Uninstall
  Delete "$INSTDIR\${PRODUCT_NAME}.url"
  Delete "$INSTDIR\uninst.exe"
  Delete "$DOCUMENTS\Aqserver\help\en\aqserver.pdf"
  Delete "$DOCUMENTS\Aqserver\help\en\aqserver.chm"
  Delete "$DOCUMENTS\Aqserver\help\de\aqserver.pdf"
  Delete "$DOCUMENTS\Aqserver\help\de\aqserver.chm"
  Delete "$DOCUMENTS\Aqserver\aqserver.cfg"
  Delete "$DOCUMENTS\Aqserver\aqserver.bat"
  Delete "$WINDIR\system32\snap7.dll"
  Delete "$INSTDIR\aqserver.exe"

  Delete "$SMPROGRAMS\Aqserver\Uninstall.lnk"
  Delete "$SMPROGRAMS\Aqserver\Website.lnk"
  Delete "$SMPROGRAMS\Aqserver\Help.lnk"
  Delete "$SMPROGRAMS\Aqserver\Help.lnk"
  Delete "$DESKTOP\Aqserver.lnk"
  Delete "$SMPROGRAMS\Aqserver\Aqserver.lnk"

  RMDir "$WINDIR\system32"
  RMDir "$SMPROGRAMS\Aqserver"
  RMDir "$INSTDIR"
  RMDir "$DOCUMENTS\Aqserver\help\en"
  RMDir "$DOCUMENTS\Aqserver\help\de"
  RMDir "$DOCUMENTS\Aqserver"

  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
  SetAutoClose true
SectionEnd