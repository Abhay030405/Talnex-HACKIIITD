'use client';
import { createCodeUsageGeneratorRegistry } from 'fumadocs-openapi/requests/generators';
import { csharp } from 'fumadocs-openapi/requests/generators/csharp';
import { curl } from 'fumadocs-openapi/requests/generators/curl';
import { go } from 'fumadocs-openapi/requests/generators/go';
import { java } from 'fumadocs-openapi/requests/generators/java';
import { javascript } from 'fumadocs-openapi/requests/generators/javascript';
import { python } from 'fumadocs-openapi/requests/generators/python';
import { createOpenAPIPage } from 'fumadocs-openapi/ui';

// Code samples for every endpoint, in this order.
const codeUsages = createCodeUsageGeneratorRegistry();
codeUsages.add('curl', curl);
codeUsages.add('js', javascript);
codeUsages.add('go', go);
codeUsages.add('python', python);
codeUsages.add('java', java);
codeUsages.add('csharp', csharp);

export const OpenAPIPage = createOpenAPIPage({ codeUsages, schemaUI: { showExample: true } });
