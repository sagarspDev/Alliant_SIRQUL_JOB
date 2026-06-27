# Sirqul Driver API Context

Source document: `Driver API Documentation Latest.pdf`

Updated from the documentation dated `Mar 3, 2026`.

## Overview

This project uses Sirqul APIs for fleet, driver, claim, work shift, notification, and reporting workflows.

The documentation is split into two areas:

- Account and Fleet Management APIs
- Driver Behavior and Reporting Services

Most non-report endpoints use the `https://fleetshare.bmrang.com:3003` base URL.
Reporting uses `https://fleetshare.bmrang.com/api/3.18/report/run`.

## Authentication

### Standard fleet, driver, claims, notification, and work shift endpoints

Required headers:

- `Application-Key: eb5cedb3d4444edae7dde06b12461c7c`
- `Authorization: Bearer <token>`
- `Content-Type: application/json` for POST/PUT bodies

Documented bearer token:

- `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjM2MzQ3MDIsImlhdCI6MTc3MjU2ODQwMiwiZXhwIjoxOTI4MDg4NDAyLCJzdWIiOiIzNjM0NzAyIn0.n-9vIkehRGQt2I8JwXx_ic83hOvjW3Cz5_PNSnlGaNk`

Notes:

- The docs do not describe how to mint or refresh the bearer token.
- The docs explicitly note that the URL format and headers differ from older documentation.

### Reporting endpoints

Required headers:

- `Application-Key: eb5cedb3d4444edae7dde06b12461c7c`
- `Application-Rest-Key: e65f1ae36e2f809bb442145fe3d72fe9`

Reporting requests use `multipart/form-data` or `application/x-www-form-urlencoded`.

## Base URLs

- Fleet / driver / claims / notifications / work shifts: `https://fleetshare.bmrang.com:3003`
- Reporting: `https://fleetshare.bmrang.com/api/3.18/report/run`
- Claims webhook callback target shown in the docs: `https://hdoapi.eoxvantage.com/prod/v1/SirqulFNOLPush`

## Common Response Shapes

### Standard object response

Many endpoints return:

```json
{
  "valid": true,
  "message": "Success",
  "item": { }
}
```

### Search / paginated response

Common search endpoints return:

```json
{
  "valid": true,
  "message": "",
  "start": 0,
  "limit": 10,
  "countTotal": 1,
  "hasMoreResults": false,
  "items": [ ]
}
```

### Reporting response

Reporting endpoints return:

```json
{
  "columns": [ ],
  "rows": [ ],
  "summations": { },
  "count": 1,
  "queryName": "GL_...",
  "version": 3.18,
  "valid": true,
  "message": "Success"
}
```

## Fleets

### Create Fleet

- Method: `POST`
- Endpoint: `/fleets`
- Content type: `application/json`

Required parameters:

- `internalFleetId` - unique Fleetlytics fleet id
- `fleetName` - fleet name

Optional parameters:

- `managerName`
- `managerPhone` - E.164 format
- `managerEmailAddress`

Important response fields:

- `item.retailerLocationId` - Sirqul fleet identifier used in later requests
- `item.internalId` - maps back to Fleetlytics `fleetId`

Example:

```bash
curl --location --request POST 'https://fleetshare.bmrang.com:3003/fleets' \
  --header 'Application-Key: eb5cedb3d4444edae7dde06b12461c7c' \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Bearer <token>' \
  --data '{
    "internalFleetId": "fleet_id_4",
    "fleetName": "Fleet Example 4",
    "managerPhone": "+15551112222"
  }'
```

### Update Fleet

- Method: `PUT`
- Endpoint: `/fleets/:retailerLocationId`
- Content type: `application/json`

Optional parameters:

- `internalFleetId`
- `fleetName`
- `workHourStart` - UTC time, updates all drivers in the fleet
- `workHourStop` - UTC time, updates all drivers in the fleet
- `additionalServices` - array of strings, updates all drivers in the fleet
- `managerName`
- `managerPhone` - E.164 format
- `managerEmailAddress`

Doc note:

- The docs say to use the Work Shift services instead of `workHourStart` / `workHourStop` for most work-hours workflows.

### Get Fleet

- Method: `GET`
- Endpoint: `/fleets/:retailerLocationId`

### Search Fleet

- Method: `GET`
- Endpoint: `/fleets/search`

Query parameters:

- `start` - pagination start index, default `0`
- `limit` - pagination limit, default `10`
- `keyword` - filters by keyword or phrase
- `internalFleetId` - search by Fleetlytics fleet id

## Drivers

### Create Driver and Assign to Fleet

- Method: `POST`
- Endpoint: `/fleets/assign`
- Content type: `application/json`

Required parameters:

- `thirdPartyId` - stable unique third-party user id
- `thirdPartyToken` - third-party access token or auth code
- `networkUID` - access provider UID
- `retailerLocationId` - Sirqul fleet id

Optional parameters:

- `thirdPartyName`
- `emailAddress`
- `cellPhone` - E.164 format
- `workShiftAudienceId`
- `additionalServices`

Important response field:

- `item.profileInfo.accountId` - Sirqul driver account id to reuse later

Example:

```bash
curl --location --request POST 'https://fleetshare.bmrang.com:3003/fleets/assign' \
  --header 'Application-Key: eb5cedb3d4444edae7dde06b12461c7c' \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Bearer <token>' \
  --data '{
    "thirdPartyId": "user_id_4",
    "thirdPartyToken": "abc1234",
    "thirdPartyName": "John Doe",
    "networkUID": "72524cbc-2774-424a-a72d-7665d105b078",
    "retailerLocationId": 353788,
    "workShiftAudienceId": 1021840,
    "additionalServices": ["SERVICE1", "SERVICE2"]
  }'
```

### Update Driver

- Method: `PUT`
- Endpoint: `/fleets/drivers/:accountId`
- Content type: `application/json`

Optional parameters:

- `firstName`
- `lastName`
- `emailAddress`
- `cellPhone` - E.164 format
- `workShiftAudienceId`
- `additionalServices`
- `active` - boolean

Doc note:

- This endpoint updates the driver but does not assign the driver to a fleet.

### Get Driver

- Method: `GET`
- Endpoint: `/fleets/drivers/:accountId`

### Search Driver

- Method: `GET`
- Endpoint: `/fleets/drivers/search`

Query parameters:

- `start` - pagination start index, default `0`
- `limit` - pagination limit, default `20`
- `keyword` - filters by keyword or phrase
- `retailerLocationId` - search drivers assigned to a specific fleet

### Delete Driver

- Method: `DELETE`
- Endpoint: `/fleets/drivers/:accountId`

Doc notes:

- The delete is destructive and cannot be undone.
- If you only want to deactivate a driver, use `active` on `PUT /fleets/drivers/:accountId`.
- The docs mention a `deleted` response field in some contexts, which is a millisecond timestamp of when the driver requested deletion.

Example delete response:

```json
{
  "valid": true,
  "message": "Employee record successfully deleted."
}
```

## Claims

### Search Claim

- Method: `GET`
- Endpoint: `/albums/search`

Use this for driver-created claims.

Required query parameters for claims:

- `albumType=driver_claim`
- `filter=ALL`

Optional query parameters:

- `albumIds` - comma-separated list of album ids
- `ownerId` - specific driver account id
- `createdSince`
- `createdBefore`
- `updatedSince`
- `updatedBefore`
- `sortField` - `ALBUM_CREATED`, `ALBUM_UPDATED`, or `ALBUM_ID`
- `descending` - default `true`
- `start`
- `limit`

Doc notes:

- `albumIds` accepts a comma-separated list.
- A claims webhook callback is documented for new claims:

```bash
curl --location --request POST 'https://hdoapi.eoxvantage.com/prod/v1/SirqulFNOLPush' \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Basic XXXX' \
  --data '{
    "albumId": 4880040
  }'
```

Important response fields:

- `item.albumId`
- `item.metaData.accidentDetails`
- `item.ownerId`
- `item.dateCreated`
- `item.dateUpdated`

## Notifications

### Send Custom Notification

- Method: `POST`
- Endpoint: `/notifications/custom`
- Content type: `application/json`

Required parameters:

- `receiverAccountIds` - array of Sirqul account ids
- `conduit` - pass `SMS` for text messages
- `customMessage`

Optional parameter:

- `appKey` - public API key to save messages to

Doc note:

- SMS delivery requires the account to have `cellPhone` populated.

Example response:

```json
{
  "valid": true,
  "message": "Success"
}
```

## Fleet Work Shifts

Work shifts are the documented way to manage driver working hours.

### Create Fleet Work Shift

- Method: `POST`
- Endpoint: `/fleets/:rId/shift`
- Content type: `application/json`

Path parameter:

- `:rId` - retailerLocationId of the fleet

Optional parameters:

- `name`

Required parameter:

- `workHours` - JSON object with day keys

`workHours` format:

```json
{
  "sunday": { "startTime": "09:45", "endTime": "22:45" },
  "monday": { "startTime": "09:45", "endTime": "22:45" },
  "tuesday": { "startTime": "09:45", "endTime": "22:45" },
  "wednesday": { "startTime": "09:45", "endTime": "22:45" },
  "thursday": { "startTime": "09:45", "endTime": "22:45" },
  "friday": { "startTime": "09:45", "endTime": "22:45" },
  "saturday": { "startTime": "09:45", "endTime": "22:45" }
}
```

Important response field:

- `item.id` - this is the `workShiftAudienceId`

### Update Fleet Work Shift

- Method: `PUT`
- Endpoint: `/fleets/:rId/shift/:aId`
- Content type: `application/json`

Path parameters:

- `:rId` - retailerLocationId of the fleet
- `:aId` - work shift id / workShiftAudienceId

Optional parameters:

- `name`

Required parameter:

- `workHours`

Doc note:

- Updating a work shift updates all drivers assigned to it.

### Get Fleet Work Shift

- Method: `GET`
- Endpoint: `/fleets/:rId/shift/:aId`

### Search Fleet Work Shift

- Method: `GET`
- Endpoint: `/fleets/:rId/shift/search`

### Delete Fleet Work Shift

- Method: `DELETE`
- Endpoint: `/fleets/:rId/shift/:aId`

Example success response:

```json
{
  "valid": true,
  "message": "Success"
}
```

## Reporting

### General Report Run

- Method: `POST`
- Endpoint: `report/run`
- Full URL used in docs: `https://fleetshare.bmrang.com/api/3.18/report/run`
- Content type: `multipart/form-data` or `application/x-www-form-urlencoded`

Required form fields:

- `query` - named query id
- `parameters` - JSON string containing query parameters

Optional form fields:

- `accountId` - account id of the user making the request
- `start` - pagination start
- `limit` - pagination limit, default `1000`
- `responseFormat` - `JSON` or `CSV`

Documented query names:

- `GL_USER_SIGNINS`
- `GL_USER_SIGNINS_BY_IDS`
- `GL_REPORT_DATA`
- `GL_LOCATION_DATA`

Additional query shown later in the document:

- `GL_LOCATION_DATA_BY_TRIP`

Usage guidelines:

- Sirqul archives activity data after 60 days.
- Reports will not return archived data older than 60 days.
- The docs recommend keeping report ranges to 45 days or less.
- The docs recommend pulling reports daily, or weekly at most.
- Use your own system if you need historical data older than 45 days.

### User sign-ins by time range

Query: `GL_USER_SIGNINS`

Parameters example:

```json
{
  "start": "2025-01-01 00:00:00",
  "end": "2025-02-01 00:00:00",
  "appKey": "eb5cedb3d4444edae7dde06b12461c7c"
}
```

Notes:

- Time values are UTC.
- The docs show the same report structure for different time windows.

### User sign-ins by account IDs

Query: `GL_USER_SIGNINS_BY_IDS`

Parameters example:

```json
{
  "userAccountIds": [2630769, 2630305],
  "appKey": "eb5cedb3d4444edae7dde06b12461c7c"
}
```

Doc notes:

- `userAccountIds` is a JSON array of longs.
- The array cannot be empty.

### Driver scores by time range

Query: `GL_REPORT_DATA`

Response fields include:

- `distance`
- `brakeIncidents`
- `lastBrakeIncident`
- `brakeScore`
- `accelIncidents`
- `lastAccelIncident`
- `accelScore`
- `speedIncidents`
- `lastSpeedIncident`
- `speedScore`
- `phoneIncidents`
- `lastPhoneIncident`
- `phoneScore`
- `turnIncidents`
- `lastTurnIncident`
- `turnScore`
- `collisionIncidents`
- `lastCollisionIncident`
- `collisionScore`
- `overallScore`

Doc note:

- `lastAccelIncident`, `lastBrakeIncident`, `lastTurnIncident`, `lastSpeedIncident`, `lastPhoneIncident`, and `lastCollisionIncident` are unix timestamps in milliseconds.
- `distance` is in meters.

### Trip scores by time range

Query: `GL_TRIP_DATA`

Response fields include:

- `tripId`
- `accountId`
- `fleetId`
- `thirdPartyId`
- `startDate`
- `endDate`
- `startLatitude`
- `startLongitude`
- `startDescription`
- `endLatitude`
- `endLongitude`
- `endDescription`
- `tripType`
- `distance`
- weather fields: `weatherCode`, `weatherTempHigh`, `weatherTempLow`, `weatherWind`
- the same incident and score fields as `GL_REPORT_DATA`

Doc notes:

- `weatherCode` is an integer linked to Weather Condition Codes and Icons.
- `weatherWind` is in kilometers per hour.
- `weatherTempHigh` and `weatherTempLow` are in celsius.
- `distance` is in meters.

### User location data

Query: `GL_LOCATION_DATA`

Response fields include:

- `analyticId`
- `accountId`
- `timestamp`
- `latitude`
- `longitude`

Doc note:

- The docs recommend querying only a day at a time or less because this report can return a lot of data.

### User location data by trip

Query: `GL_LOCATION_DATA_BY_TRIP`

Parameters example:

```json
{
  "appKey": "eb5cedb3d4444edae7dde06b12461c7c",
  "tripId": "D2D64BFA-8D9B-4BB6-91C9-3F1E5FA5A387"
}
```

Response fields include:

- `accountId`
- `timestamp`
- `latitude`
- `longitude`
- `tripId`

## Practical Curls

When generating curl commands, preserve these patterns:

- Use the `:retailerLocationId`, `:accountId`, `:rId`, and `:aId` path parameters exactly as documented.
- Use JSON bodies for fleet/driver/notification/work shift endpoints.
- Use form fields for `report/run`.
- Include `Application-Key` and bearer auth on standard endpoints.
- Include `Application-Rest-Key` on reporting endpoints instead of the bearer token.

## Known Documentation Gaps and Caveats

- No auth bootstrap or token refresh flow is documented.
- Error codes and failure payloads are not documented.
- Some example payloads are truncated or inconsistent in type labeling, especially in report schemas.
- Some response fields appear in examples but are not fully described in the parameter tables.
- `workHourStart` / `workHourStop` on fleet update are described as legacy-ish convenience fields; the docs prefer work shift endpoints.
- The reporting endpoint path in examples includes `/api/3.18/`; the top-level reporting access info only lists the host.

## Operational Reminder

Keep this file updated whenever new API behavior is discovered from:

- the PDF documentation
- live API responses
- curl tests against the Sirqul service

When new response shapes or edge cases are observed, add them here so future requests can be answered consistently.

Codex agent definition:

- `api_agent/codex_api_agent.toml`
