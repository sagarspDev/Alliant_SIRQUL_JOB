# Sirqul Driver API Cheat Sheet

Source: `Driver API Documentation Latest.pdf`

## Base URLs

- Standard API: `https://fleetshare.bmrang.com:3003`
- Reporting API: `https://fleetshare.bmrang.com/api/3.18/report/run`

## Auth Headers

### Standard endpoints

- `Application-Key: eb5cedb3d4444edae7dde06b12461c7c`
- `Authorization: Bearer <token>`

### Reporting endpoints

- `Application-Key: eb5cedb3d4444edae7dde06b12461c7c`
- `Application-Rest-Key: e65f1ae36e2f809bb442145fe3d72fe9`

## Fleet Endpoints

| Action | Method | Path | Key Params |
| --- | --- | --- | --- |
| Create fleet | `POST` | `/fleets` | `internalFleetId`, `fleetName` |
| Update fleet | `PUT` | `/fleets/:retailerLocationId` | `fleetName`, `workHourStart`, `workHourStop`, `additionalServices`, `managerName`, `managerPhone`, `managerEmailAddress` |
| Get fleet | `GET` | `/fleets/:retailerLocationId` | path id |
| Search fleets | `GET` | `/fleets/search` | `start`, `limit`, `keyword`, `internalFleetId` |

## Driver Endpoints

| Action | Method | Path | Key Params |
| --- | --- | --- | --- |
| Create and assign driver | `POST` | `/fleets/assign` | `thirdPartyId`, `thirdPartyToken`, `networkUID`, `retailerLocationId`, optional `thirdPartyName`, `emailAddress`, `cellPhone`, `workShiftAudienceId`, `additionalServices` |
| Update driver | `PUT` | `/fleets/drivers/:accountId` | `firstName`, `lastName`, `emailAddress`, `cellPhone`, `workShiftAudienceId`, `additionalServices`, `active` |
| Get driver | `GET` | `/fleets/drivers/:accountId` | path id |
| Search drivers | `GET` | `/fleets/drivers/search` | `start`, `limit`, `keyword`, `retailerLocationId` |
| Delete driver | `DELETE` | `/fleets/drivers/:accountId` | path id |

## Claim Endpoint

| Action | Method | Path | Key Params |
| --- | --- | --- | --- |
| Search claims | `GET` | `/albums/search` | `albumType=driver_claim`, `filter=ALL`, optional `albumIds`, `ownerId`, `createdSince`, `createdBefore`, `updatedSince`, `updatedBefore`, `sortField`, `descending`, `start`, `limit` |

## Notification Endpoint

| Action | Method | Path | Key Params |
| --- | --- | --- | --- |
| Send custom notification | `POST` | `/notifications/custom` | `receiverAccountIds`, `conduit`, `customMessage`, optional `appKey` |

## Work Shift Endpoints

| Action | Method | Path | Key Params |
| --- | --- | --- | --- |
| Create shift | `POST` | `/fleets/:rId/shift` | `workHours`, optional `name` |
| Update shift | `PUT` | `/fleets/:rId/shift/:aId` | `workHours`, optional `name` |
| Get shift | `GET` | `/fleets/:rId/shift/:aId` | path ids |
| Search shifts | `GET` | `/fleets/:rId/shift/search` | path id |
| Delete shift | `DELETE` | `/fleets/:rId/shift/:aId` | path ids |

## Reporting Queries

| Query | Use Case | Main Parameters |
| --- | --- | --- |
| `GL_USER_SIGNINS` | sign-ins by time range | `start`, `end`, `appKey` |
| `GL_USER_SIGNINS_BY_IDS` | sign-ins by account ids | `userAccountIds`, `appKey` |
| `GL_REPORT_DATA` | driver scores by time range | `start`, `end`, `appKey` |
| `GL_TRIP_DATA` | trip scores by time range | `start`, `end`, `appKey` |
| `GL_LOCATION_DATA` | user location data by time range | `start`, `end`, `appKey` |
| `GL_LOCATION_DATA_BY_TRIP` | user location data for a trip | `tripId`, `appKey` |

## Response Patterns

- Standard success: `{ "valid": true, "message": "Success", "item": { ... } }`
- Search success: `{ "valid": true, "start": 0, "limit": 10, "countTotal": 1, "hasMoreResults": false, "items": [ ... ] }`
- Report success: `{ "columns": [ ... ], "rows": [ ... ], "summations": { ... }, "count": 1, "queryName": "...", "valid": true }`

## High-Value IDs

- Fleet id used in paths: `retailerLocationId`
- Driver id used in paths: `accountId`
- Work shift id used in paths: `workShiftAudienceId` returned as `item.id`
- Fleet lookup id in Fleetlytics payloads: `internalFleetId`
- Driver lookup id in Fleetlytics payloads: `thirdPartyId`

## Practical Notes

- `managerPhone` and `cellPhone` should be E.164 format.
- Work shifts are the preferred way to manage driver hours.
- Reporting data is archived after 60 days; the docs recommend querying within 45 days.
- `albumIds` for claims is comma-separated.
- `GL_LOCATION_DATA` can be large; query a day or less at a time.
- The docs do not provide failure payload examples or token refresh instructions.
