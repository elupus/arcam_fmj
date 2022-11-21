from arcam.fmj.utils import get_udn_from_xml, get_possibly_invalid_xml, get_uniqueid_from_udn

code = """
<root xmlns="urn:schemas-upnp-org:device-1-0" xmlns:pnpx="http://schemas.microsoft.com/windows/pnpx/2005/11" xmlns:microsoft="urn:schemas-microsoft-com:WMPNSS-1-0" xmlns:df="http://schemas.microsoft.com/windows/2008/09/devicefoundation">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<device>
<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
<presentationURL>/web</presentationURL>
<pnpx:X_hardwareId>VEN_2A2D&DEV_0001&SUBSYS_0001&REV_01 VEN_0033&DEV_0005&REV_01</pnpx:X_hardwareId>
<pnpx:X_compatibleId>MS_DigitalMediaDeviceClass_DMR_V001</pnpx:X_compatibleId>
<pnpx:X_deviceCategory>MediaDevices</pnpx:X_deviceCategory>
<df:X_deviceCategory>Multimedia.DMR</df:X_deviceCategory>
<microsoft:magicPacketWakeSupported>0</microsoft:magicPacketWakeSupported>
<microsoft:magicPacketSendSupported>1</microsoft:magicPacketSendSupported>
<dlna:X_DLNADOC xmlns:dlna="urn:schemas-dlna-org:device-1-0">DMR-1.50</dlna:X_DLNADOC>
<friendlyName>Arcam media client 002261a55190</friendlyName>
<manufacturer>A & R Cambridge</manufacturer>
<manufacturerURL>http://www.arcam.co.uk</manufacturerURL>
<modelDescription>ir-ser-FS2026-0200-0115_V2.2.14.37060-8</modelDescription>
<modelName> </modelName>
<modelNumber> </modelNumber>
<modelURL>http://www.arcamradio.co.uk</modelURL>
<serialNumber>0b05031407351f2701005201xxxxxxxx</serialNumber>
<UDN>uuid:3dcc7100-f76c-11dd-87af-xxxxxxxxxxx</UDN>
<iconList>
<icon>
<mimetype>image/png</mimetype>
<width>48</width>
<height>48</height>
<depth>32</depth>
<url>/icon.png</url>
</icon>
<icon>
<mimetype>image/jpeg</mimetype>
<width>48</width>
<height>48</height>
<depth>32</depth>
<url>/icon.jpg</url>
</icon>
<icon>
<mimetype>image/png</mimetype>
<width>120</width>
<height>120</height>
<depth>32</depth>
<url>/icon2.png</url>
</icon>
<icon>
<mimetype>image/jpeg</mimetype>
<width>120</width>
<height>120</height>
<depth>32</depth>
<url>/icon2.jpg</url>
</icon>
</iconList>
<serviceList>
<service>
<serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
<serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
<SCPDURL>AVTransport/scpd.xml</SCPDURL>
<controlURL>AVTransport/control</controlURL>
<eventSubURL>AVTransport/event</eventSubURL>
</service>
<service>
<serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>
<serviceId>urn:upnp-org:serviceId:ConnectionManager</serviceId>
<SCPDURL>ConnectionManager/scpd.xml</SCPDURL>
<controlURL>ConnectionManager/control</controlURL>
<eventSubURL>ConnectionManager/event</eventSubURL>
</service>
<service>
<serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
<serviceId>urn:upnp-org:serviceId:RenderingControl</serviceId>
<SCPDURL>RenderingControl/scpd.xml</SCPDURL>
<controlURL>RenderingControl/control</controlURL>
<eventSubURL>RenderingControl/event</eventSubURL>
</service>
</serviceList>
</device>
</root>
"""

print(get_uniqueid_from_udn(get_udn_from_xml(get_possibly_invalid_xml(code))))